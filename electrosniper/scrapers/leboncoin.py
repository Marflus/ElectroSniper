from __future__ import annotations

import logging
import uuid
from typing import Any

from electrosniper.config import Settings
from electrosniper.http_client import StealthSession, jitter_sleep
from electrosniper.models import RawListing
from electrosniper.scrapers.base import BaseScraper, ScraperBlockedError

logger = logging.getLogger(__name__)

LBC_API_URL = "https://api.leboncoin.fr/finder/search"
LBC_API_KEY = "ba0c2dad52b3ec"

LBC_QUERY_POOL: list[dict[str, Any]] = [
    {"cat": "43", "condition": "5", "q": ""},
    {"cat": "15", "condition": "5", "q": ""},
    {"cat": "16", "condition": "5", "q": ""},
    {"cat": "20", "condition": "5", "q": ""},
    {"cat": "21", "condition": "5", "q": ""},
    {"cat": "43", "condition": None, "q": "hs"},
    {"cat": "15", "condition": None, "q": "pc portable hs"},
    {"cat": "16", "condition": None, "q": "ampli hs"},
    {"cat": "21", "condition": None, "q": "makita hs"},
    {"cat": "20", "condition": None, "q": "delonghi hs"},
]


def run_lbc_solve_interactive() -> None:
    print(
        "Methode fiable pour debloquer Leboncoin depuis ton VRAI navigateur Chrome :\n"
        "  1. Ouvre https://www.leboncoin.fr/ dans ton Chrome habituel\n"
        "  2. Appuie sur F12 -> onglet Application -> Cookies -> https://www.leboncoin.fr\n"
        "  3. Copie la valeur du cookie 'datadome'\n"
        "  4. Colle-la dans ElectroSniper -> Parametres -> Cookie DataDome Leboncoin -> Enregistrer"
    )


class LeboncoinScraper(BaseScraper):
    name = "leboncoin"

    def __init__(self, queries_per_cycle: int = 5) -> None:
        self._cursor = 0
        self._queries_per_cycle = queries_per_cycle
        self._device_uuid = str(uuid.uuid4())

    def _next_batch(self) -> list[dict[str, Any]]:
        batch = []
        for _ in range(min(self._queries_per_cycle, len(LBC_QUERY_POOL))):
            batch.append(LBC_QUERY_POOL[self._cursor % len(LBC_QUERY_POOL)])
            self._cursor = (self._cursor + 1) % len(LBC_QUERY_POOL)
        return batch

    def _parse_ad(self, ad: dict[str, Any]) -> RawListing | None:
        if not isinstance(ad, dict):
            return None
        list_id = str(ad.get("list_id") or "").strip()
        title = str(ad.get("subject") or "").strip()
        if not list_id or not title:
            return None

        price_raw = ad.get("price")
        price = 0.0
        if isinstance(price_raw, list) and price_raw:
            try:
                price = float(price_raw[0])
            except (TypeError, ValueError):
                price = 0.0
        elif isinstance(price_raw, (int, float)):
            price = float(price_raw)

        attrs = ad.get("attributes") or []
        attr_map: dict[str, dict[str, Any]] = {}
        for a in attrs:
            if isinstance(a, dict) and a.get("key"):
                attr_map[str(a["key"])] = a

        shippable = False
        shipping_price: float | None = None
        shipping_modes: list[str] = []

        if "shippable" in attr_map:
            shippable = str(attr_map["shippable"].get("value", "")).lower() == "true"

        non_ship_tokens = {"face_to_face", "hand_delivery", "main_propre", "remise en main propre", "pickup"}
        if "shipping_type" in attr_map:
            st = attr_map["shipping_type"]
            vals = st.get("values_label") or st.get("values") or []
            raw_modes = [str(v).strip() for v in vals if v] if isinstance(vals, list) else (
                [str(st["value_label"]).strip()] if st.get("value_label") else []
            )
            shipping_modes = [
                m for m in raw_modes
                if m.lower() not in non_ship_tokens and "main propre" not in m.lower()
            ]
            if shipping_modes:
                shippable = True
            elif raw_modes and "shippable" not in attr_map:
                shippable = False

        for cost_key in ("shipping_cost", "delivery_cost", "shipping_price"):
            if cost_key in attr_map:
                try:
                    shipping_price = float(attr_map[cost_key].get("value"))
                    shippable = True
                except (TypeError, ValueError):
                    pass

        if ad.get("has_delivery") is True:
            shippable = True

        if shippable:
            if shipping_price is not None:
                shipping_note = f"{shipping_price:.2f} €"
            elif shipping_modes:
                shipping_note = f"Livraison LBC ({', '.join(shipping_modes[:2])}, ~4-8€)"
            else:
                shipping_note = "Livraison LBC dispo (~4-8€)"
        else:
            shipping_note = "Main propre uniquement"

        condition_label = ""
        if "item_condition" in attr_map:
            condition_label = str(
                attr_map["item_condition"].get("value_label")
                or attr_map["item_condition"].get("value")
                or ""
            )

        images = ad.get("images") or {}
        img_url = ""
        if isinstance(images, dict):
            urls = images.get("urls_large") or images.get("urls") or []
            img_url = str(urls[0]) if urls else str(images.get("thumb_url") or "")

        loc = ad.get("location") or {}
        location = str(loc.get("city_label") or loc.get("city") or "")

        owner = ad.get("owner") or {}
        seller_name = str(owner.get("name") or "")

        url = str(ad.get("url") or f"https://www.leboncoin.fr/ad/offres/{list_id}")

        return RawListing(
            site=self.name,
            external_id=list_id,
            title=title,
            description=str(ad.get("body") or "").strip(),
            price=price,
            url=url,
            image_url=img_url,
            location=location,
            published_at=str(ad.get("first_publication_date") or ad.get("index_date") or ""),
            shipping_available=shippable,
            shipping_price=shipping_price,
            shipping_note=shipping_note,
            raw_category=str(ad.get("category_name") or ""),
            condition_label=condition_label,
            seller_name=seller_name,
        )

    def _build_payload(self, item: dict[str, Any], settings: Settings) -> dict[str, Any]:
        enums: dict[str, Any] = {"ad_type": ["offer"]}
        if item.get("condition"):
            enums["item_condition"] = [item["condition"]]

        filters: dict[str, Any] = {
            "category": {"id": item["cat"]},
            "enums": enums,
            "ranges": {
                "price": {
                    "min": int(settings.min_price_eur),
                    "max": int(settings.max_price_eur),
                }
            },
        }
        if item.get("q"):
            filters["keywords"] = {"text": item["q"], "type": "all"}

        return {
            "limit": 30,
            "limit_alu": 0,
            "sort_by": "time",
            "sort_order": "desc",
            "filters": filters,
        }

    def _run_batch(
        self, batch: list[dict[str, Any]], settings: Settings, headers: dict[str, str], *, mobile: bool
    ) -> tuple[list[RawListing], int]:
        session = StealthSession(timeout=20.0, mobile=mobile)
        results: dict[str, RawListing] = {}
        last_status = 200
        try:
            for idx, item in enumerate(batch):
                if idx > 0:
                    jitter_sleep(3.5, 6.5)

                resp = session.post(
                    LBC_API_URL, headers=headers, json=self._build_payload(item, settings)
                )
                last_status = resp.status_code
                if resp.status_code in (403, 429):
                    return list(results.values()), resp.status_code
                if resp.status_code != 200:
                    logger.warning("Leboncoin HTTP %s pour %s", resp.status_code, item)
                    continue

                for ad in resp.json().get("ads") or []:
                    parsed = self._parse_ad(ad)
                    if parsed:
                        results[parsed.external_id] = parsed
        finally:
            session.close()
        return list(results.values()), last_status

    def scan(self, settings: Settings) -> list[RawListing]:
        batch = self._next_batch()
        dd_cookie = settings.lbc_datadome_cookie.strip()
        if dd_cookie.lower().startswith("datadome="):
            dd_cookie = dd_cookie.split("=", 1)[1].strip()

        if dd_cookie:
            web_headers = {
                "api_key": LBC_API_KEY,
                "Content-Type": "application/json",
                "Accept": "*/*",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
                "Origin": "https://www.leboncoin.fr",
                "Referer": "https://www.leboncoin.fr/",
                "Cookie": f"datadome={dd_cookie}",
            }
            items, code = self._run_batch(batch, settings, web_headers, mobile=False)
            if items or code == 200:
                return items

        mobile_headers = {
            "api_key": LBC_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "User-Agent": f"LBC;iOS;17.5.1;iPhone;phone;{self._device_uuid};wifi;6.101.0",
        }
        items, code = self._run_batch(batch, settings, mobile_headers, mobile=True)
        if items or code == 200:
            return items

        raise ScraperBlockedError(
            f"Leboncoin anti-bot (HTTP {code}) : copie ton cookie 'datadome' depuis ton vrai Chrome "
            "(F12 -> Application -> Cookies -> leboncoin.fr) et colle-le dans Paramètres (⚙️)."
        )
