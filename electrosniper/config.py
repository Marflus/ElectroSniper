from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "electrosniper.db"
FB_PROFILE_DIR = DATA_DIR / "fb_profile"


def _as_bool(val: str | None, default: bool) -> bool:
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on", "oui"}


def _as_int(val: str | None, default: int) -> int:
    try:
        return int(val) if val is not None and val.strip() != "" else default
    except ValueError:
        return default


def _as_float(val: str | None, default: float) -> float:
    try:
        return float(val) if val is not None and val.strip() != "" else default
    except ValueError:
        return default


def is_valid_api_key(key: str) -> bool:
    k = (key or "").strip()
    if not k or len(k) < 16:
        return False
    if "xxxx" in k.lower() or k.lower().startswith("your_"):
        return False
    return True


@dataclass
class Settings:
    anthropic_api_key: str
    anthropic_triage_model: str
    anthropic_deep_model: str

    telegram_bot_token: str
    telegram_chat_id: str

    scan_interval_minutes: int
    min_alert_score: int
    min_alert_profit_eur: float
    min_price_eur: float
    max_price_eur: float
    max_ai_per_cycle: int
    require_shipping: bool
    exclude_already_opened: bool

    enable_leboncoin: bool
    enable_vinted: bool
    enable_facebook: bool
    enable_ebay: bool

    lbc_datadome_cookie: str
    fb_city: str

    ebay_client_id: str
    ebay_client_secret: str

    web_host: str
    web_port: int


def load_settings(db_overrides: dict[str, str] | None = None) -> Settings:
    load_dotenv(BASE_DIR / ".env", override=False)
    ov = db_overrides or {}

    def get(key: str, default: str = "") -> str:
        if key in ov and ov[key] is not None:
            return str(ov[key])
        return os.getenv(key, default)

    raw_key = get("ANTHROPIC_API_KEY", "").strip()
    clean_key = raw_key if is_valid_api_key(raw_key) else ""

    return Settings(
        anthropic_api_key=clean_key,
        anthropic_triage_model=get("ANTHROPIC_TRIAGE_MODEL", "claude-haiku-5-5").strip(),
        anthropic_deep_model=get("ANTHROPIC_DEEP_MODEL", "claude-sonnet-5-5").strip(),
        telegram_bot_token=get("TELEGRAM_BOT_TOKEN", "").strip(),
        telegram_chat_id=get("TELEGRAM_CHAT_ID", "").strip(),
        scan_interval_minutes=max(5, _as_int(get("SCAN_INTERVAL_MINUTES", "10"), 10)),
        min_alert_score=max(0, min(100, _as_int(get("MIN_ALERT_SCORE", "72"), 72))),
        min_alert_profit_eur=max(0.0, _as_float(get("MIN_ALERT_PROFIT_EUR", "30"), 30.0)),
        min_price_eur=max(0.0, _as_float(get("MIN_PRICE_EUR", "10"), 10.0)),
        max_price_eur=max(10.0, _as_float(get("MAX_PRICE_EUR", "500"), 500.0)),
        max_ai_per_cycle=max(1, _as_int(get("MAX_AI_PER_CYCLE", "20"), 20)),
        require_shipping=_as_bool(get("REQUIRE_SHIPPING", "true"), True),
        exclude_already_opened=_as_bool(get("EXCLUDE_ALREADY_OPENED", "false"), False),
        enable_leboncoin=_as_bool(get("ENABLE_LEBONCOIN", "true"), True),
        enable_vinted=_as_bool(get("ENABLE_VINTED", "true"), True),
        enable_facebook=_as_bool(get("ENABLE_FACEBOOK", "false"), False),
        enable_ebay=_as_bool(get("ENABLE_EBAY", "false"), False),
        lbc_datadome_cookie=get("LBC_DATADOME_COOKIE", "").strip(),
        fb_city=get("FB_CITY", "france").strip().lower(),
        ebay_client_id=get("EBAY_CLIENT_ID", "").strip(),
        ebay_client_secret=get("EBAY_CLIENT_SECRET", "").strip(),
        web_host=get("WEB_HOST", "127.0.0.1").strip(),
        web_port=_as_int(get("WEB_PORT", "8765"), 8765),
    )
