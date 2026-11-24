from __future__ import annotations

import asyncio
import logging
import math
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from electrosniper.db import Database
from electrosniper.engine import ScanEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

db = Database()
engine = ScanEngine(db)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    engine.start()
    try:
        yield
    finally:
        await engine.stop()


app = FastAPI(title="ElectroSniper", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


class StatusUpdatePayload(BaseModel):
    user_status: str | None = None
    user_notes: str | None = None


class SettingsUpdatePayload(BaseModel):
    SCAN_INTERVAL_MINUTES: int | None = None
    MIN_ALERT_SCORE: int | None = None
    MIN_ALERT_PROFIT_EUR: float | None = None
    MIN_PRICE_EUR: float | None = None
    MAX_PRICE_EUR: float | None = None
    REQUIRE_SHIPPING: bool | None = None
    EXCLUDE_ALREADY_OPENED: bool | None = None
    ENABLE_LEBONCOIN: bool | None = None
    ENABLE_VINTED: bool | None = None
    ENABLE_FACEBOOK: bool | None = None
    ENABLE_EBAY: bool | None = None
    LBC_DATADOME_COOKIE: str | None = None
    FB_CITY: str | None = None


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    return engine.status_payload()


@app.get("/api/listings")
def get_listings(
    search: str = "",
    site: str = "all",
    category: str = "all",
    status: str = "active",
    min_score: int = Query(default=0, ge=0, le=100),
    show_rejected: bool = False,
    only_opened: bool = False,
    sort: str = "score",
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=20),
) -> dict[str, Any]:
    settings = engine.get_settings()
    effective_min = settings.min_alert_score if status == "gems" else min_score
    offset = (page - 1) * limit
    items, total = db.list_listings_paginated(
        search=search,
        site=site,
        category=category,
        status=status,
        min_score=effective_min,
        show_rejected=show_rejected,
        only_opened=only_opened,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    total_pages = max(1, math.ceil(total / limit))
    return {
        "items": items,
        "count": len(items),
        "total": total,
        "page": page,
        "page_size": limit,
        "total_pages": total_pages,
    }


@app.get("/api/listings/{listing_id}")
def get_listing(listing_id: int) -> dict[str, Any]:
    item = db.get_listing(listing_id)
    if not item:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    return item


@app.post("/api/listings/{listing_id}/status")
def update_listing_status(listing_id: int, payload: StatusUpdatePayload) -> dict[str, Any]:
    if payload.user_status is not None and payload.user_status not in {
        "new",
        "favorite",
        "ignored",
        "bought",
    }:
        raise HTTPException(status_code=400, detail="Statut invalide")

    ok = db.update_user_status(listing_id, status=payload.user_status, notes=payload.user_notes)
    if not ok:
        raise HTTPException(status_code=404, detail="Annonce introuvable")
    return {"ok": True, "item": db.get_listing(listing_id)}


@app.post("/api/listings/{listing_id}/deep-analyze")
async def deep_analyze_listing(listing_id: int) -> dict[str, Any]:
    listing = db.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Annonce introuvable")

    settings = engine.get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=400,
            detail="Ajoute ta vraie clé ANTHROPIC_API_KEY dans le fichier .env puis redémarre.",
        )

    try:
        result = await asyncio.to_thread(engine.analyzer.deep_analyze_listing, listing, settings)
        db.update_deep_analysis(listing_id, result)
        return {"ok": True, "item": db.get_listing(listing_id)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Erreur analyse approfondie : {exc}")


@app.post("/api/scan/trigger")
def trigger_scan() -> dict[str, Any]:
    if engine.paused:
        engine.resume()
    else:
        engine.trigger_now()
    return {"ok": True}


@app.post("/api/ai/triage-now")
async def trigger_triage_now() -> dict[str, Any]:
    settings = engine.get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=400,
            detail="Clé ANTHROPIC_API_KEY manquante ou invalide dans .env (remplace sk-ant-xxxx...).",
        )
    if engine.scanning:
        raise HTTPException(status_code=409, detail="Un scan ou une notation est déjà en cours.")
    asyncio.create_task(engine.run_triage_only())
    pending = db.count_pending_triage()
    return {"ok": True, "message": f"Notation IA lancée sur toutes les annonces en attente ({pending})"}


@app.post("/api/scan/pause")
def pause_scan() -> dict[str, Any]:
    engine.pause()
    return {"ok": True, "paused": True}


@app.post("/api/scan/resume")
def resume_scan() -> dict[str, Any]:
    engine.resume()
    return {"ok": True, "paused": False}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    s = engine.get_settings()
    return {
        "SCAN_INTERVAL_MINUTES": s.scan_interval_minutes,
        "MIN_ALERT_SCORE": s.min_alert_score,
        "MIN_ALERT_PROFIT_EUR": s.min_alert_profit_eur,
        "MIN_PRICE_EUR": s.min_price_eur,
        "MAX_PRICE_EUR": s.max_price_eur,
        "REQUIRE_SHIPPING": s.require_shipping,
        "EXCLUDE_ALREADY_OPENED": s.exclude_already_opened,
        "ENABLE_LEBONCOIN": s.enable_leboncoin,
        "ENABLE_VINTED": s.enable_vinted,
        "ENABLE_FACEBOOK": s.enable_facebook,
        "ENABLE_EBAY": s.enable_ebay,
        "LBC_DATADOME_COOKIE": s.lbc_datadome_cookie,
        "FB_CITY": s.fb_city,
        "ANTHROPIC_TRIAGE_MODEL": s.anthropic_triage_model,
        "ANTHROPIC_DEEP_MODEL": s.anthropic_deep_model,
        "EBAY_API_READY": bool(s.ebay_client_id and s.ebay_client_secret),
    }


@app.post("/api/settings")
def update_settings(payload: SettingsUpdatePayload) -> dict[str, Any]:
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if updates:
        db.set_settings(updates)
        if "LBC_DATADOME_COOKIE" in updates:
            db.update_site_health("leboncoin", "Prêt", ok=True, cooldown_until=None, error="")
    return {"ok": True, "settings": get_settings()}


@app.post("/api/telegram/test")
async def test_telegram() -> dict[str, Any]:
    settings = engine.get_settings()
    ok, msg = await asyncio.to_thread(engine.notifier.send_test, settings)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "message": "Notification de test envoyée sur Telegram !"}


@app.get("/api/logs")
def get_logs() -> dict[str, Any]:
    return {"logs": db.get_scan_logs(limit=60)}
