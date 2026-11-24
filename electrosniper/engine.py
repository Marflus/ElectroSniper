from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta, timezone

from electrosniper.ai_analyzer import AIAnalyzer
from electrosniper.config import Settings, load_settings
from electrosniper.db import Database
from electrosniper.filters import evaluate_listing
from electrosniper.models import RawListing
from electrosniper.notifier import TelegramNotifier
from electrosniper.scrapers import (
    BaseScraper,
    EbayScraper,
    FacebookScraper,
    LeboncoinScraper,
    ScraperBlockedError,
    VintedScraper,
)

logger = logging.getLogger(__name__)


class ScanEngine:
    def __init__(self, db: Database) -> None:
        self.db = db
        self.analyzer = AIAnalyzer(db)
        self.notifier = TelegramNotifier()
        self.scrapers: dict[str, BaseScraper] = {
            "leboncoin": LeboncoinScraper(),
            "vinted": VintedScraper(),
            "facebook": FacebookScraper(),
            "ebay": EbayScraper(),
        }
        self.paused: bool = False
        self.scanning: bool = False
        self.current_step: str = "En attente"
        self.last_ai_error: str = ""
        self.last_scan_at: datetime | None = None
        self.next_scan_at: datetime | None = None
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._scan_lock = asyncio.Lock()
        self._task: asyncio.Task | None = None

    def get_settings(self) -> Settings:
        return load_settings(self.db.get_all_settings())

    def refilter_existing(self) -> int:
        """Ré-applique le filtre local (qui a pu évoluer) aux annonces pas encore classées."""
        settings = self.get_settings()
        changed = 0
        for row in self.db.iter_untouched_listings():
            raw = RawListing(
                site=row["site"],
                external_id=row["external_id"],
                title=row["title"] or "",
                description=row["description"] or "",
                price=float(row["price"] or 0),
                url=row["url"] or "",
                shipping_available=bool(row["shipping_available"]),
                shipping_price=row["shipping_price"],
                shipping_note=row["shipping_note"] or "",
            )
            flt = evaluate_listing(raw, settings)
            # Seules les exclusions strictes (accessoire, téléphone, TV...) sont ré-appliquées :
            # l'état "pour pièces" du site n'est pas stocké, on ne peut donc pas rejuger le reste.
            if row["filter_passed"] and not flt.accepted and flt.reject_reason.startswith("Exclu"):
                flt.already_opened = bool(row["already_opened"])
                flt.opened_reason = row["opened_reason"] or ""
                flt.category = row["category"] or flt.category
                self.db.update_filter_result(row["id"], flt)
                changed += 1
        if changed:
            logger.info("Filtre local ré-appliqué : %s annonces mises à jour", changed)
        return changed

    def start(self) -> None:
        try:
            self.refilter_existing()
        except Exception:
            logger.exception("Ré-application du filtre impossible")
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except Exception:
                self._task.cancel()

    def trigger_now(self) -> None:
        self._wake_event.set()

    def pause(self) -> None:
        self.paused = True
        self.current_step = "En pause"

    def resume(self) -> None:
        self.paused = False
        self.current_step = "Reprise programmée"
        self._wake_event.set()

    def _site_enabled(self, site: str, settings: Settings) -> bool:
        if site == "leboncoin":
            return settings.enable_leboncoin
        if site == "vinted":
            return settings.enable_vinted
        if site == "facebook":
            return settings.enable_facebook
        if site == "ebay":
            return settings.enable_ebay and bool(
                settings.ebay_client_id and settings.ebay_client_secret
            )
        return False

    def _is_in_cooldown(self, site: str) -> tuple[bool, str]:
        health = self.db.get_site_health().get(site)
        if not health or not health.get("cooldown_until"):
            return False, ""
        try:
            until = datetime.fromisoformat(health["cooldown_until"])
            now = datetime.now(timezone.utc)
            if now < until:
                mins = max(1, int((until - now).total_seconds() // 60))
                return True, f"Cooldown anti-bot ({mins} min restantes)"
        except ValueError:
            pass
        return False, ""

    async def _loop(self) -> None:
        await asyncio.sleep(3)
        while not self._stop_event.is_set():
            if not self.paused:
                await self.run_cycle()

            settings = self.get_settings()
            base_sec = settings.scan_interval_minutes * 60
            jitter = random.randint(-45, 120)
            wait_sec = max(240, base_sec + jitter)
            self.next_scan_at = datetime.now(timezone.utc) + timedelta(seconds=wait_sec)
            if not self.paused:
                self.current_step = "En attente du prochain scan"

            self._wake_event.clear()
            try:
                await asyncio.wait_for(self._wake_event.wait(), timeout=wait_sec)
            except asyncio.TimeoutError:
                pass

    async def _run_triage_batch(self, settings: Settings, *, limit: int | None = None) -> tuple[int, int]:
        effective_limit = limit if limit is not None else settings.max_ai_per_cycle
        pending = self.db.get_pending_triage(limit=effective_limit)
        if not pending:
            return 0, 0
        if not settings.anthropic_api_key:
            self.last_ai_error = "Ajoute ta vraie clé ANTHROPIC_API_KEY dans .env (remplace sk-ant-xxxx...)."
            self.db.log_scan(
                "ai_triage",
                "warning",
                message=f"{len(pending)} offres en attente : clé ANTHROPIC_API_KEY manquante ou invalide dans .env.",
            )
            return 0, 0

        analyzed_count = 0
        alerted_count = 0
        self.last_ai_error = ""
        total_to_process = len(pending)

        for i, listing in enumerate(pending, start=1):
            if self._stop_event.is_set() or self.paused:
                break
            self.current_step = f"Notation IA ({i}/{total_to_process})..."
            try:
                triage = await asyncio.to_thread(
                    self.analyzer.triage_listing, listing, settings
                )
                self.db.update_triage(listing["id"], triage)
                analyzed_count += 1

                should_alert = triage.verdict == "GO"
                if should_alert:
                    fresh = self.db.get_listing(listing["id"])
                    if fresh and not fresh.get("notified_at"):
                        sent = await asyncio.to_thread(
                            self.notifier.send_deal_alert, fresh, settings
                        )
                        if sent:
                            self.db.mark_notified(listing["id"])
                            alerted_count += 1
            except Exception as exc:
                logger.exception("Erreur triage IA pour listing #%s", listing["id"])
                self.last_ai_error = str(exc)[:220]
                self.db.log_scan("ai_triage", "error", message=str(exc)[:300])
                break

        if analyzed_count > 0:
            self.db.log_scan(
                "ai_triage",
                "ok",
                analyzed_count=analyzed_count,
                alerted_count=alerted_count,
                message=f"{analyzed_count} offres notées, {alerted_count} alertes Telegram.",
            )
        return analyzed_count, alerted_count

    async def run_triage_only(self) -> tuple[int, int]:
        if self._scan_lock.locked():
            return 0, 0
        async with self._scan_lock:
            self.scanning = True
            try:
                settings = self.get_settings()
                # Le bouton manuel 'Noter IA' note TOUTES les annonces en attente
                total_pending = self.db.count_pending_triage()
                return await self._run_triage_batch(settings, limit=max(1, total_pending))
            finally:
                self.scanning = False
                if not self.paused:
                    self.current_step = "En attente du prochain scan"

    async def run_cycle(self) -> None:
        if self._scan_lock.locked():
            return

        async with self._scan_lock:
            self.scanning = True
            settings = self.get_settings()
            cycle_found = 0
            cycle_kept = 0

            try:
                for site_name, scraper in self.scrapers.items():
                    if not self._site_enabled(site_name, settings):
                        status_txt = (
                            "Clé API manquante"
                            if site_name == "ebay" and settings.enable_ebay
                            else "Désactivé"
                        )
                        self.db.update_site_health(site_name, status_txt, ok=True, added_found=0)
                        continue

                    in_cd, cd_msg = self._is_in_cooldown(site_name)
                    if in_cd:
                        self.db.log_scan(site_name, "cooldown", message=cd_msg)
                        continue

                    self.current_step = f"Scan {site_name.capitalize()}..."
                    try:
                        raw_items = await asyncio.to_thread(scraper.scan, settings)
                        raw_total = len(raw_items)
                        found = 0
                        kept = 0
                        for raw in raw_items:
                            if self.db.listing_exists(raw.site, raw.external_id):
                                if raw.image_url:
                                    self.db.backfill_image(raw.site, raw.external_id, raw.image_url)
                                continue
                            found += 1
                            flt = evaluate_listing(raw, settings)
                            inserted_id = self.db.insert_listing(raw, flt)
                            if inserted_id and flt.accepted:
                                kept += 1

                        cycle_found += found
                        cycle_kept += kept
                        self.db.set_settings(
                            {"LAST_SCAN_FOUND": cycle_found, "LAST_SCAN_KEPT": cycle_kept}
                        )

                        self.db.update_site_health(
                            site_name, "OK", ok=True, cooldown_until=None, error="", added_found=found
                        )
                        self.db.log_scan(
                            site_name,
                            "ok",
                            found_count=found,
                            kept_count=kept,
                            message=f"{raw_total} brutes lues, {found} nouvelles, {kept} retenues par le filtre.",
                        )
                    except ScraperBlockedError as exc:
                        health = self.db.get_site_health().get(site_name) or {}
                        errs = int(health.get("consecutive_errors", 0)) + 1
                        cd_minutes = min(180, 30 * (2 ** (errs - 1)))
                        until = (datetime.now(timezone.utc) + timedelta(minutes=cd_minutes)).isoformat(
                            timespec="seconds"
                        )
                        self.db.update_site_health(
                            site_name,
                            f"Cooldown {cd_minutes}m",
                            ok=False,
                            cooldown_until=until,
                            error=str(exc),
                        )
                        self.db.log_scan(
                            site_name,
                            "blocked",
                            message=f"{exc} -> pause de {cd_minutes} min",
                        )
                    except Exception as exc:
                        logger.exception("Erreur scraper %s", site_name)
                        self.db.update_site_health(site_name, "Erreur", ok=False, error=str(exc))
                        self.db.log_scan(site_name, "error", message=str(exc))

                self.db.set_settings(
                    {"LAST_SCAN_FOUND": cycle_found, "LAST_SCAN_KEPT": cycle_kept}
                )

                await self._run_triage_batch(settings)
                self.last_scan_at = datetime.now(timezone.utc)
            finally:
                self.scanning = False
                if not self.paused:
                    self.current_step = "En attente du prochain scan"

    def status_payload(self) -> dict:
        settings = self.get_settings()
        now = datetime.now(timezone.utc)
        seconds_left = None
        if self.next_scan_at and not self.paused and not self.scanning:
            seconds_left = max(0, int((self.next_scan_at - now).total_seconds()))

        site_health = self.db.get_site_health()
        for site_name in self.scrapers.keys():
            enabled = self._site_enabled(site_name, settings)
            cur = site_health.get(site_name)
            if enabled:
                if not cur or cur.get("status") == "Désactivé":
                    site_health[site_name] = {
                        **(cur or {"site": site_name}),
                        "status": "Prêt",
                    }
            else:
                label = (
                    "Clé API manquante"
                    if site_name == "ebay" and settings.enable_ebay
                    else "Désactivé"
                )
                site_health[site_name] = {**(cur or {"site": site_name}), "status": label}

        return {
            "paused": self.paused,
            "scanning": self.scanning,
            "current_step": self.current_step,
            "last_ai_error": self.last_ai_error,
            "pending_ai_count": self.db.count_pending_triage(),
            "last_scan_at": self.last_scan_at.isoformat(timespec="seconds") if self.last_scan_at else None,
            "next_scan_in_seconds": seconds_left,
            "anthropic_configured": bool(settings.anthropic_api_key),
            "telegram_configured": self.notifier.is_configured(settings),
            "min_alert_score": settings.min_alert_score,
            "stats": self.db.get_stats(settings.min_alert_score),
            "site_health": site_health,
            "api_cost": self.db.get_api_cost_summary(),
        }
