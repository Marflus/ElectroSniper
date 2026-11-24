from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from electrosniper.config import DB_PATH
from electrosniper.models import DeepAnalysisResult, FilterResult, RawListing, TriageResult
from electrosniper.scoring import SCORE_VERSION

# Colonnes ajoutées après la première version (migration automatique)
EXTRA_LISTING_COLUMNS: dict[str, str] = {
    "success_pct": "INTEGER",
    "profit_if_success_eur": "REAL",
    "max_loss_eur": "REAL",
    "max_buy_price_eur": "REAL",
    "score_version": "INTEGER DEFAULT 0",
}

# Une annonce est à (re)noter si jamais notée, ou notée avec un ancien algorithme
# (sauf si une analyse approfondie existe : on ne l'écrase pas automatiquement).
PENDING_TRIAGE_SQL = (
    "filter_passed = 1 AND (ai_analyzed = 0 OR "
    "(COALESCE(score_version, 0) < ? AND deep_analysis_json IS NULL))"
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, db_path=DB_PATH) -> None:
        self.db_path = db_path
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.execute("PRAGMA foreign_keys=ON;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    site TEXT NOT NULL,
                    external_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    price REAL NOT NULL,
                    shipping_available INTEGER DEFAULT 0,
                    shipping_price REAL,
                    shipping_note TEXT DEFAULT '',
                    url TEXT NOT NULL,
                    image_url TEXT DEFAULT '',
                    location TEXT DEFAULT '',
                    published_at TEXT DEFAULT '',
                    seller_name TEXT DEFAULT '',
                    category TEXT DEFAULT 'autre',
                    filter_passed INTEGER DEFAULT 0,
                    reject_reason TEXT DEFAULT '',
                    already_opened INTEGER DEFAULT 0,
                    opened_reason TEXT DEFAULT '',

                    ai_analyzed INTEGER DEFAULT 0,
                    ai_score INTEGER,
                    repair_score INTEGER,
                    resale_score INTEGER,
                    margin_score INTEGER,
                    estimated_resale_eur REAL,
                    estimated_parts_eur REAL,
                    estimated_profit_eur REAL,
                    suspected_fault TEXT DEFAULT '',
                    ai_verdict TEXT DEFAULT '',
                    ai_reasoning TEXT DEFAULT '',
                    ai_model TEXT DEFAULT '',

                    deep_analysis_json TEXT,
                    deep_analyzed_at TEXT,

                    user_status TEXT DEFAULT 'new',
                    user_notes TEXT DEFAULT '',
                    notified_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,

                    UNIQUE(site, external_id)
                );

                CREATE INDEX IF NOT EXISTS idx_listings_filter_score
                    ON listings(filter_passed, ai_score DESC, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_listings_status
                    ON listings(user_status);
                CREATE INDEX IF NOT EXISTS idx_listings_site
                    ON listings(site);

                CREATE TABLE IF NOT EXISTS scan_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    site TEXT NOT NULL,
                    status TEXT NOT NULL,
                    found_count INTEGER DEFAULT 0,
                    kept_count INTEGER DEFAULT 0,
                    analyzed_count INTEGER DEFAULT 0,
                    alerted_count INTEGER DEFAULT 0,
                    message TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS site_health (
                    site TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    last_ok_at TEXT,
                    cooldown_until TEXT,
                    consecutive_errors INTEGER DEFAULT 0,
                    last_error TEXT DEFAULT '',
                    total_found INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    model TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            existing = {r["name"] for r in conn.execute("PRAGMA table_info(listings)").fetchall()}
            for col, ddl in EXTRA_LISTING_COLUMNS.items():
                if col not in existing:
                    conn.execute(f"ALTER TABLE listings ADD COLUMN {col} {ddl}")

            # Annonces Facebook étrangères (prix en PLN) : inachetables depuis la France
            conn.execute(
                """
                UPDATE listings
                SET filter_passed = 0,
                    reject_reason = 'Annonce étrangère (Facebook hors France, prix en PLN)'
                WHERE site = 'facebook' AND description LIKE '%converti depuis PLN%'
                """
            )

    def listing_exists(self, site: str, external_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM listings WHERE site = ? AND external_id = ?",
                (site, external_id),
            ).fetchone()
            return row is not None

    def backfill_image(self, site: str, external_id: str, image_url: str) -> None:
        if not image_url:
            return
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE listings
                SET image_url = ?, updated_at = ?
                WHERE site = ? AND external_id = ? AND (image_url IS NULL OR image_url = '')
                """,
                (image_url, utc_now_iso(), site, external_id),
            )

    def insert_listing(self, raw: RawListing, flt: FilterResult) -> int | None:
        now = utc_now_iso()
        with self.connect() as conn:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO listings (
                        site, external_id, title, description, price,
                        shipping_available, shipping_price, shipping_note,
                        url, image_url, location, published_at, seller_name,
                        category, filter_passed, reject_reason,
                        already_opened, opened_reason, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        raw.site,
                        raw.external_id,
                        raw.title,
                        raw.description,
                        raw.price,
                        1 if raw.shipping_available else 0,
                        raw.shipping_price,
                        raw.shipping_note,
                        raw.url,
                        raw.image_url,
                        raw.location,
                        raw.published_at,
                        raw.seller_name,
                        flt.category,
                        1 if flt.accepted else 0,
                        flt.reject_reason,
                        1 if flt.already_opened else 0,
                        flt.opened_reason,
                        now,
                        now,
                    ),
                )
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                return None

    def update_triage(self, listing_id: int, res: TriageResult) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE listings SET
                    ai_analyzed = 1,
                    ai_score = ?,
                    repair_score = ?,
                    resale_score = ?,
                    margin_score = ?,
                    estimated_resale_eur = ?,
                    estimated_parts_eur = ?,
                    estimated_profit_eur = ?,
                    suspected_fault = ?,
                    ai_verdict = ?,
                    ai_reasoning = ?,
                    ai_model = ?,
                    success_pct = ?,
                    profit_if_success_eur = ?,
                    max_loss_eur = ?,
                    max_buy_price_eur = ?,
                    score_version = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    res.score,
                    res.repair_score,
                    res.resale_score,
                    res.margin_score,
                    res.estimated_resale_eur,
                    res.estimated_parts_eur,
                    res.estimated_profit_eur,
                    res.suspected_fault,
                    res.verdict,
                    res.reasoning,
                    res.model,
                    res.success_pct,
                    res.profit_if_success_eur,
                    res.max_loss_eur,
                    res.max_buy_price_eur,
                    res.score_version,
                    now,
                    listing_id,
                ),
            )

    def update_deep_analysis(self, listing_id: int, res: DeepAnalysisResult) -> None:
        now = utc_now_iso()
        payload = json.dumps(res.__dict__, ensure_ascii=False)
        verdict_map = {"ACHETER": "GO", "NEGOCIER": "A_VOIR", "LAISSER_TOMBER": "PASS"}
        ai_verdict = verdict_map.get(res.verdict, "A_VOIR")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE listings SET
                    ai_analyzed = 1,
                    ai_score = ?,
                    repair_score = ?,
                    resale_score = ?,
                    margin_score = ?,
                    estimated_resale_eur = ?,
                    estimated_parts_eur = ?,
                    estimated_profit_eur = ?,
                    suspected_fault = ?,
                    ai_verdict = ?,
                    ai_reasoning = ?,
                    ai_model = ?,
                    success_pct = ?,
                    profit_if_success_eur = ?,
                    max_loss_eur = ?,
                    max_buy_price_eur = ?,
                    score_version = ?,
                    deep_analysis_json = ?,
                    deep_analyzed_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    res.score,
                    res.repair_score,
                    res.resale_score,
                    res.margin_score,
                    res.estimated_resale_eur,
                    res.estimated_parts_eur,
                    res.estimated_net_profit_eur,
                    res.suspected_fault,
                    ai_verdict,
                    res.summary[:400],
                    res.model,
                    res.success_pct,
                    res.profit_if_success_eur,
                    res.max_loss_eur,
                    res.recommended_max_buy_eur,
                    res.score_version,
                    payload,
                    now,
                    now,
                    listing_id,
                ),
            )

    def mark_notified(self, listing_id: int) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            conn.execute(
                "UPDATE listings SET notified_at = ?, updated_at = ? WHERE id = ?",
                (now, now, listing_id),
            )

    def update_user_status(
        self, listing_id: int, status: str | None = None, notes: str | None = None
    ) -> bool:
        now = utc_now_iso()
        with self.connect() as conn:
            if status is not None and notes is not None:
                cur = conn.execute(
                    "UPDATE listings SET user_status = ?, user_notes = ?, updated_at = ? WHERE id = ?",
                    (status, notes, now, listing_id),
                )
            elif status is not None:
                cur = conn.execute(
                    "UPDATE listings SET user_status = ?, updated_at = ? WHERE id = ?",
                    (status, now, listing_id),
                )
            elif notes is not None:
                cur = conn.execute(
                    "UPDATE listings SET user_notes = ?, updated_at = ? WHERE id = ?",
                    (notes, now, listing_id),
                )
            else:
                return False
            return cur.rowcount > 0

    def get_pending_triage(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM listings
                WHERE {PENDING_TRIAGE_SQL}
                ORDER BY ai_analyzed ASC, created_at DESC
                LIMIT ?
                """,
                (SCORE_VERSION, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def count_pending_triage(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM listings WHERE {PENDING_TRIAGE_SQL}", (SCORE_VERSION,)
            ).fetchone()
            return int(row["c"] or 0)

    def iter_untouched_listings(self) -> list[dict[str, Any]]:
        """Annonces pas encore classées par l'utilisateur (pour ré-appliquer le filtre local)."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM listings WHERE user_status = 'new' "
                "AND reject_reason NOT LIKE 'Annonce étrangère%'"
            ).fetchall()
            return [dict(r) for r in rows]

    def update_filter_result(self, listing_id: int, flt: FilterResult) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE listings SET filter_passed = ?, reject_reason = ?, category = ?,
                    already_opened = ?, opened_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    1 if flt.accepted else 0,
                    flt.reject_reason,
                    flt.category,
                    1 if flt.already_opened else 0,
                    flt.opened_reason,
                    utc_now_iso(),
                    listing_id,
                ),
            )

    def get_listing(self, listing_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
            if not row:
                return None
            return self._hydrate_listing(dict(row))

    def _hydrate_listing(self, item: dict[str, Any]) -> dict[str, Any]:
        raw_deep = item.get("deep_analysis_json")
        if raw_deep:
            try:
                item["deep_analysis"] = json.loads(raw_deep)
            except json.JSONDecodeError:
                item["deep_analysis"] = None
        else:
            item["deep_analysis"] = None
        item["shipping_available"] = bool(item.get("shipping_available"))
        item["filter_passed"] = bool(item.get("filter_passed"))
        item["already_opened"] = bool(item.get("already_opened"))
        item["ai_analyzed"] = bool(item.get("ai_analyzed"))
        return item

    def list_listings_paginated(
        self,
        *,
        search: str = "",
        site: str = "all",
        category: str = "all",
        status: str = "active",
        min_score: int = 0,
        show_rejected: bool = False,
        only_opened: bool = False,
        sort: str = "score",
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        where = []
        params: list[Any] = []

        if show_rejected:
            where.append("filter_passed = 0")
        else:
            where.append("filter_passed = 1")
            if status == "active":
                where.append("user_status != 'ignored'")
            elif status == "gems":
                where.append("user_status != 'ignored'")
            elif status in {"new", "favorite", "ignored", "bought"}:
                where.append("user_status = ?")
                params.append(status)

        if site and site != "all":
            where.append("site = ?")
            params.append(site)

        if category and category != "all":
            where.append("category = ?")
            params.append(category)

        if min_score > 0 and not show_rejected:
            where.append("COALESCE(ai_score, 0) >= ?")
            params.append(min_score)

        if only_opened:
            where.append("already_opened = 1")

        if search.strip():
            like = f"%{search.strip()}%"
            where.append("(title LIKE ? OR description LIKE ? OR suspected_fault LIKE ?)")
            params.extend([like, like, like])

        order_map = {
            "score": "(COALESCE(score_version, 0) >= 2 OR deep_analysis_json IS NOT NULL) DESC, COALESCE(ai_score, -1) DESC, created_at DESC",
            "recent": "created_at DESC",
            "profit": "COALESCE(estimated_profit_eur, -999) DESC, COALESCE(ai_score, -1) DESC",
            "price_asc": "price ASC, COALESCE(ai_score, -1) DESC",
        }
        order_sql = order_map.get(sort, order_map["score"])
        where_sql = " AND ".join(where) if where else "1=1"

        with self.connect() as conn:
            total_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM listings WHERE {where_sql}",
                tuple(params),
            ).fetchone()
            total = int(total_row["c"] or 0)

            rows = conn.execute(
                f"SELECT * FROM listings WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            ).fetchall()
            return [self._hydrate_listing(dict(r)) for r in rows], total

    def get_stats(self, min_alert_score: int) -> dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_scanned,
                    SUM(CASE WHEN filter_passed = 1 THEN 1 ELSE 0 END) AS total_kept,
                    SUM(CASE WHEN filter_passed = 0 THEN 1 ELSE 0 END) AS total_rejected,
                    SUM(CASE WHEN filter_passed = 1 AND ai_analyzed = 1 THEN 1 ELSE 0 END) AS total_analyzed,
                    SUM(CASE WHEN filter_passed = 1 AND COALESCE(ai_score, 0) >= ? AND user_status != 'ignored' THEN 1 ELSE 0 END) AS total_gems,
                    SUM(CASE WHEN user_status = 'favorite' THEN 1 ELSE 0 END) AS total_favorites,
                    SUM(CASE WHEN notified_at IS NOT NULL THEN 1 ELSE 0 END) AS total_notified
                FROM listings
                """,
                (min_alert_score,),
            ).fetchone()
            res = {k: (row[k] or 0) for k in row.keys()}
            meta = conn.execute(
                "SELECT key, value FROM app_settings WHERE key IN ('LAST_SCAN_FOUND', 'LAST_SCAN_KEPT')"
            ).fetchall()
            meta_map = {r["key"]: int(r["value"]) for r in meta if str(r["value"]).isdigit()}
            res["last_scan_found"] = meta_map.get("LAST_SCAN_FOUND", 0)
            res["last_scan_kept"] = meta_map.get("LAST_SCAN_KEPT", 0)
            return res

    def log_scan(
        self,
        site: str,
        status: str,
        found_count: int = 0,
        kept_count: int = 0,
        analyzed_count: int = 0,
        alerted_count: int = 0,
        message: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO scan_logs (
                    created_at, site, status, found_count, kept_count,
                    analyzed_count, alerted_count, message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    utc_now_iso(),
                    site,
                    status,
                    found_count,
                    kept_count,
                    analyzed_count,
                    alerted_count,
                    message,
                ),
            )

    def get_scan_logs(self, limit: int = 60) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scan_logs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def update_site_health(
        self,
        site: str,
        status: str,
        *,
        ok: bool = False,
        cooldown_until: str | None = None,
        error: str = "",
        added_found: int = 0,
    ) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM site_health WHERE site = ?", (site,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO site_health (
                        site, status, last_ok_at, cooldown_until,
                        consecutive_errors, last_error, total_found
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        site,
                        status,
                        now if ok else None,
                        cooldown_until,
                        0 if ok else 1,
                        error,
                        added_found,
                    ),
                )
            else:
                errors = 0 if ok else (existing["consecutive_errors"] + 1)
                last_ok = now if ok else existing["last_ok_at"]
                total = (existing["total_found"] or 0) + added_found
                conn.execute(
                    """
                    UPDATE site_health SET
                        status = ?,
                        last_ok_at = ?,
                        cooldown_until = ?,
                        consecutive_errors = ?,
                        last_error = ?,
                        total_found = ?
                    WHERE site = ?
                    """,
                    (status, last_ok, cooldown_until, errors, error, total, site),
                )

    def get_site_health(self) -> dict[str, dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM site_health").fetchall()
            return {r["site"]: dict(r) for r in rows}

    def log_api_usage(
        self, model: str, purpose: str, input_tokens: int, output_tokens: int, cost_usd: float
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO api_usage (
                    created_at, model, purpose, input_tokens, output_tokens, cost_usd
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), model, purpose, input_tokens, output_tokens, cost_usd),
            )

    def get_api_cost_summary(self) -> dict[str, Any]:
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self.connect() as conn:
            total = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS cost, COUNT(*) AS calls FROM api_usage"
            ).fetchone()
            today = conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS cost, COUNT(*) AS calls FROM api_usage WHERE created_at LIKE ?",
                (f"{today_prefix}%",),
            ).fetchone()
            return {
                "total_usd": round(float(total["cost"]), 4),
                "total_calls": int(total["calls"]),
                "today_usd": round(float(today["cost"]), 4),
                "today_calls": int(today["calls"]),
            }

    def get_all_settings(self) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            return {r["key"]: r["value"] for r in rows}

    def set_settings(self, values: dict[str, Any]) -> None:
        with self.connect() as conn:
            for key, val in values.items():
                if isinstance(val, bool):
                    sval = "true" if val else "false"
                else:
                    sval = str(val)
                conn.execute(
                    """
                    INSERT INTO app_settings (key, value) VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (key, sval),
                )
