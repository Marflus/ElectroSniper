from __future__ import annotations

import base64
import logging
import time
from typing import Any

import httpx

from electrosniper.config import Settings
from electrosniper.http_client import jitter_sleep
from electrosniper.models import RawListing
from electrosniper.scrapers.base import BaseScraper, ScraperBlockedError

logger = logging.getLogger(__name__)

EBAY_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
EBAY_BROWSE_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"

EBAY_QUERIES = [
    "console playstation nintendo xbox",
    "pc portable macbook",
    "carte graphique rtx",
    "makita dewalt milwaukee",
    "appareil photo reflex hybride",
    "ampli hifi casque audio",
    "delonghi dyson kitchenaid",
]


class EbayScraper(BaseScraper):
    """Prêt à l'emploi dès que EBAY_CLIENT_ID et EBAY_CLIENT_SECRET sont dans .env."""

    name = "ebay"

    def __init__(self) -> None:
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._cursor: int = 0

    def _get_token(self, client: httpx.Client, client_id: str, client_secret: str) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        creds = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
        resp = client.post(
            EBAY_TOKEN_URL,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": "https://api.ebay.com/oauth/api_scope",
            },
        )
        if resp.status_code != 200:
            raise ScraperBlockedError(f"Erreur OAuth eBay (HTTP {resp.status_code})")

        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + int(data.get("expires_in", 7200))
        return self._token

    def _parse_item(self, item: dict[str, Any]) -> RawListing | None:
        item_id = str(item.get("itemId") or "").strip()
        title = str(item.get("title") or "").strip()
        if not item_id or not title:
            return None

        price_obj = item.get("price") or {}
        try:
            price = float(price_obj.get("value", 0))
        except (TypeError, ValueError):
            price = 0.0

        shipping_opts = item.get("shippingOptions") or []
        shippable = bool(shipping_opts)
        shipping_price: float | None = None
        shipping_note = "Livraison eBay"
        if shipping_opts:
            cost_obj = shipping_opts[0].get("shippingCost") or {}
            try:
                shipping_price = float(cost_obj.get("value", 0))
                shipping_note = (
                    "Livraison gratuite" if shipping_price == 0 else f"{shipping_price:.2f} €"
                )
            except (TypeError, ValueError):
                shipping_price = None

        img = item.get("image") or {}
        loc = item.get("itemLocation") or {}
        seller = item.get("seller") or {}

        return RawListing(
            site=self.name,
            external_id=item_id,
            title=title,
            description=str(item.get("shortDescription") or item.get("condition") or ""),
            price=price,
            url=str(item.get("itemWebUrl") or ""),
            image_url=str(img.get("imageUrl") or ""),
            location=f"{loc.get('postalCode', '')} {loc.get('country', '')}".strip(),
            published_at=str(item.get("itemCreationDate") or ""),
            shipping_available=shippable,
            shipping_price=shipping_price,
            shipping_note=shipping_note,
            condition_label=str(item.get("condition") or "Pour pièces"),
            seller_name=str(seller.get("username") or ""),
        )

    def scan(self, settings: Settings) -> list[RawListing]:
        if not settings.enable_ebay:
            return []
        if not settings.ebay_client_id or not settings.ebay_client_secret:
            return []

        results: dict[str, RawListing] = {}
        with httpx.Client(timeout=20.0) as client:
            token = self._get_token(client, settings.ebay_client_id, settings.ebay_client_secret)
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_FR",
            }
            for idx in range(3):
                if idx > 0:
                    jitter_sleep(1.5, 3.0)
                q = EBAY_QUERIES[self._cursor % len(EBAY_QUERIES)]
                self._cursor = (self._cursor + 1) % len(EBAY_QUERIES)

                flt = (
                    f"conditions:{{7000}},buyingOptions:{{FIXED_PRICE}},"
                    f"price:[{int(settings.min_price_eur)}..{int(settings.max_price_eur)}],"
                    f"priceCurrency:EUR,deliveryCountry:FR"
                )
                resp = client.get(
                    EBAY_BROWSE_URL,
                    headers=headers,
                    params={"q": q, "filter": flt, "sort": "newlyListed", "limit": 25},
                )
                if resp.status_code in (403, 429):
                    raise ScraperBlockedError(f"eBay API limitée (HTTP {resp.status_code})")
                if resp.status_code != 200:
                    continue

                for item in resp.json().get("itemSummaries") or []:
                    parsed = self._parse_item(item)
                    if parsed:
                        results[parsed.external_id] = parsed

        return list(results.values())
