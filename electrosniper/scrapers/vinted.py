from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlencode

from electrosniper.config import DATA_DIR, Settings
from electrosniper.http_client import StealthSession, jitter_sleep, launch_stealth_context
from electrosniper.models import RawListing
from electrosniper.scrapers.base import BaseScraper, ScraperBlockedError

logger = logging.getLogger(__name__)

VINTED_HOME = "https://www.vinted.fr/"
VINTED_SEARCH_API = "https://www.vinted.fr/api/v2/catalog/items"
VINTED_PROFILE_DIR = DATA_DIR / "vinted_profile"

VINTED_QUERY_POOL: list[str] = [
    "console hs",
    "ps4 hs",
    "ps5 hs",
    "nintendo switch hs",
    "manette hs",
    "pc portable hs",
    "macbook hs",
    "ipad hs",
    "appareil photo hs",
    "casque bose hs",
    "makita hs",
    "dyson hs",
    "delonghi hs",
]

DOM_EXTRACT_JS = """
() => {
  const seen = new Set();
  const out = [];
  const links = document.querySelectorAll('a[href*="/items/"]');
  for (const a of links) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/\\/items\\/(\\d+)/);
    if (!m || seen.has(m[1])) continue;
    seen.add(m[1]);

    // Remonter jusqu'au conteneur de la carte pour trouver la vraie photo produit
    let imgUrl = '';
    let node = a;
    for (let depth = 0; depth < 5 && node; depth++) {
      const imgs = node.querySelectorAll ? node.querySelectorAll('img') : [];
      for (const im of imgs) {
        const src = im.currentSrc || im.getAttribute('src') || im.getAttribute('data-src') || '';
        if (src && src.startsWith('http') && !src.includes('avatar') && !src.includes('svg')) {
          imgUrl = src;
          break;
        }
      }
      if (imgUrl) break;
      node = node.parentElement;
    }

    out.push({
      id: m[1],
      href: href,
      titleAttr: a.getAttribute('title') || '',
      text: (a.innerText || (node ? node.innerText : '') || '').trim(),
      img: imgUrl,
    });
    if (out.length >= 30) break;
  }
  return out;
}
"""


class VintedScraper(BaseScraper):
    name = "vinted"

    def __init__(self, queries_per_cycle: int = 4) -> None:
        self._cursor = 0
        self._queries_per_cycle = queries_per_cycle

    def _next_batch(self) -> list[str]:
        batch = []
        for _ in range(min(self._queries_per_cycle, len(VINTED_QUERY_POOL))):
            batch.append(VINTED_QUERY_POOL[self._cursor % len(VINTED_QUERY_POOL)])
            self._cursor = (self._cursor + 1) % len(VINTED_QUERY_POOL)
        return batch

    @staticmethod
    def _extract_price(val: Any) -> float:
        if isinstance(val, dict):
            val = val.get("amount") or val.get("value") or 0
        try:
            cleaned = re.sub(r"[^0-9,\.]", "", str(val)).replace(",", ".")
            return float(cleaned) if cleaned else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _parse_item(self, item: dict[str, Any]) -> RawListing | None:
        item_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not item_id or not title:
            return None

        price = self._extract_price(item.get("price"))
        total_with_fee = self._extract_price(item.get("total_item_price"))
        fee_part = max(0.0, round(total_with_fee - price, 2)) if total_with_fee > price else 0.0

        est_shipping = 4.20 + fee_part
        shipping_note = (
            f"~{est_shipping:.2f} € (port ~4.20€ + prot. {fee_part:.2f}€)"
            if fee_part > 0
            else "Livraison Vinted (~3.50-5.50€ + frais)"
        )

        brand = str(item.get("brand_title") or "").strip()
        status = str(item.get("status") or "").strip()
        desc_parts = [
            p
            for p in [
                f"Marque : {brand}" if brand else "",
                f"État Vinted : {status}" if status else "",
            ]
            if p
        ]
        description = " | ".join(desc_parts)

        photo = item.get("photo") or {}
        img_url = str(photo.get("full_size_url") or photo.get("url") or "")
        if not img_url and isinstance(photo.get("thumbnails"), list) and photo["thumbnails"]:
            img_url = str(photo["thumbnails"][-1].get("url") or "")

        user = item.get("user") or {}
        seller = str(user.get("login") or "")
        url = str(item.get("url") or f"https://www.vinted.fr/items/{item_id}")

        return RawListing(
            site=self.name,
            external_id=item_id,
            title=title,
            description=description,
            price=price,
            url=url,
            image_url=img_url,
            location="France / UE (Vinted)",
            published_at="",
            shipping_available=True,
            shipping_price=round(est_shipping, 2),
            shipping_note=shipping_note,
            condition_label=status,
            seller_name=seller,
        )

    def _scan_via_http(self, batch: list[str], settings: Settings) -> list[RawListing] | None:
        session = StealthSession(timeout=18.0)
        results: dict[str, RawListing] = {}
        got_any_200 = False
        try:
            home_resp = session.get(VINTED_HOME, headers={"Accept-Language": "fr-FR,fr;q=0.9"})
            if home_resp.status_code in (403, 429):
                return None
            jitter_sleep(1.2, 2.5)
            headers = {
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "fr-FR,fr;q=0.9",
                "Referer": VINTED_HOME,
            }
            for idx, q in enumerate(batch):
                if idx > 0:
                    jitter_sleep(2.5, 5.0)
                params = {
                    "search_text": q,
                    "order": "newest_first",
                    "per_page": 25,
                    "page": 1,
                    "price_from": int(settings.min_price_eur),
                    "price_to": int(settings.max_price_eur),
                    "currency": "EUR",
                }
                resp = session.get(VINTED_SEARCH_API, headers=headers, params=params)
                if resp.status_code in (401, 403, 429):
                    return None
                if resp.status_code != 200:
                    continue
                got_any_200 = True
                for item in resp.json().get("items") or []:
                    parsed = self._parse_item(item)
                    if parsed:
                        results[parsed.external_id] = parsed
        except Exception as exc:
            logger.debug("Vinted HTTP fallback -> Playwright: %s", exc)
            return None
        finally:
            session.close()

        return list(results.values()) if (got_any_200 and results) else None

    def _scan_via_playwright(self, batch: list[str], settings: Settings) -> list[RawListing]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ScraperBlockedError("Vinted nécessite Playwright pour obtenir le jeton de session.")

        results: dict[str, RawListing] = {}
        with sync_playwright() as p:
            ctx = launch_stealth_context(p, VINTED_PROFILE_DIR, headless=True, use_system_channel=False)
            try:
                page = ctx.new_page()
                captured_items: list[dict[str, Any]] = []

                def on_response(resp: Any) -> None:
                    try:
                        if "/api/v2/catalog/items" in resp.url and resp.status == 200:
                            data = resp.json()
                            if isinstance(data, dict) and data.get("items"):
                                captured_items.extend(data["items"])
                    except Exception:
                        pass

                page.on("response", on_response)

                for idx, q in enumerate(batch[:3]):
                    if idx > 0:
                        jitter_sleep(3.0, 5.5)

                    captured_items.clear()
                    params = {
                        "search_text": q,
                        "order": "newest_first",
                        "price_from": int(settings.min_price_eur),
                        "price_to": int(settings.max_price_eur),
                        "currency": "EUR",
                    }
                    url = f"https://www.vinted.fr/catalog?{urlencode(params)}"
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)

                    try:
                        page.wait_for_selector('a[href*="/items/"]', timeout=10000)
                    except Exception:
                        pass
                    jitter_sleep(2.5, 4.0)

                    try:
                        btn = page.locator("#onetrust-accept-btn-handler").first
                        if btn.is_visible(timeout=700):
                            btn.click(timeout=1500)
                            jitter_sleep(0.8, 1.2)
                    except Exception:
                        pass

                    for item in captured_items:
                        parsed = self._parse_item(item)
                        if parsed:
                            results[parsed.external_id] = parsed

                    # Extraction DOM enrichie avec la vraie photo produit
                    dom_cards = page.evaluate(DOM_EXTRACT_JS) or []
                    for c in dom_cards:
                        try:
                            item_id = str(c.get("id") or "")
                            if not item_id:
                                continue
                            img_url = str(c.get("img") or "")
                            if item_id in results:
                                if not results[item_id].image_url and img_url:
                                    results[item_id].image_url = img_url
                                continue

                            blob = c.get("titleAttr") or c.get("text") or ""
                            price_m = re.search(r"(\d+(?:[,\.]\d{1,2})?)\s*€", blob)
                            if not price_m:
                                continue
                            price = float(price_m.group(1).replace(",", "."))
                            title = blob.split(",")[0].strip()
                            if not title:
                                continue
                            href = str(c.get("href") or "")
                            full_url = href if href.startswith("http") else f"https://www.vinted.fr{href}"
                            results[item_id] = RawListing(
                                site=self.name,
                                external_id=item_id,
                                title=title,
                                description=f"Annonce Vinted ({q})",
                                price=price,
                                url=full_url,
                                image_url=img_url,
                                location="France / UE (Vinted)",
                                shipping_available=True,
                                shipping_price=4.90,
                                shipping_note="Livraison Vinted (~4-6€)",
                            )
                        except Exception:
                            continue
            finally:
                ctx.close()

        return list(results.values())

    def scan(self, settings: Settings) -> list[RawListing]:
        batch = self._next_batch()
        http_res = self._scan_via_http(batch, settings)
        if http_res is not None:
            return http_res
        return self._scan_via_playwright(batch, settings)
