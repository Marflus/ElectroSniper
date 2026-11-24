from __future__ import annotations

import logging
import re
import time
from typing import Any
from urllib.parse import quote_plus

from electrosniper.config import FB_PROFILE_DIR, Settings
from electrosniper.filters import CATEGORY_KEYWORDS, DEFECT_SIGNALS, normalize_text
from electrosniper.http_client import jitter_sleep, launch_stealth_context
from electrosniper.models import RawListing
from electrosniper.scrapers.base import BaseScraper, ScraperBlockedError

logger = logging.getLogger(__name__)

PLN_TO_EUR_RATE = 4.25

# 8 pôles régionaux couvrant toute la France métropolitaine
FRANCE_CITY_HUBS = [
    "paris",
    "lyon",
    "marseille",
    "toulouse",
    "bordeaux",
    "nantes",
    "lille",
    "strasbourg",
]

FB_QUERIES = [
    "console hs",
    "ps4 hs",
    "ps5 hs",
    "nintendo switch hs",
    "pc portable hs",
    "macbook hs",
    "makita hs",
    "appareil photo hs",
    "ampli hs",
    "dyson hs",
    "machine cafe hs",
]

NO_SHIPPING_PATTERNS = [
    r"\bmain propre uniquement\b",
    r"\bremise en main propre uniquement\b",
    r"\buniquement en main propre\b",
    r"\bpas d envoi\b",
    r"\baucun envoi\b",
    r"\bsans envoi\b",
    r"\bpas de livraison\b",
    r"\bsur place uniquement\b",
    r"\ba venir chercher uniquement\b",
    r"\bretrait sur place uniquement\b",
]

SHIPPING_OK_PATTERNS = [
    r"\benvoi possible\b",
    r"\blivraison possible\b",
    r"\blivraison disponible\b",
    r"\benvoi mondial relay\b",
    r"\bmondial relay\b",
    r"\bcolissimo\b",
    r"\bchronopost\b",
    r"\bshop2shop\b",
    r"\bexpedition possible\b",
    r"\bpeut etre envoye\b",
    r"\bje peux envoyer\b",
    r"\benvoi soigne\b",
    r"\bfrais de port\b",
    r"\bport en sus\b",
    r"\bachetez maintenant\b",
]


def run_fb_login_interactive() -> None:
    """Ouvre Chromium persistant pour se connecter une fois à Facebook Marketplace."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "[ERREUR] Playwright n'est pas installé.\n"
            "Exécute : pip install playwright && playwright install chromium"
        )
        return

    print(
        "Ouverture de Chromium... Connecte-toi a Facebook Marketplace, attends que "
        "les annonces s'affichent, puis ferme simplement la fenetre."
    )
    with sync_playwright() as p:
        ctx = launch_stealth_context(p, FB_PROFILE_DIR, headless=False, use_system_channel=False)
        page = ctx.new_page()
        page.goto("https://www.facebook.com/marketplace/paris/", timeout=45000)
        try:
            page.wait_for_event("close", timeout=0)
        except Exception:
            pass
        ctx.close()
    print("Session Facebook sauvegardée dans data/fb_profile.")


class FacebookScraper(BaseScraper):
    """Scraper Facebook Marketplace France entière avec vérification de livraison."""

    name = "facebook"

    def __init__(self) -> None:
        self._query_cursor = 0
        self._city_cursor = 0
        self._last_run_ts: float = 0.0

    @staticmethod
    def _parse_price(line: str) -> tuple[float | None, str]:
        """Retourne (prix_en_eur, devise_origine). Gère €, EUR, zł, zl, PLN."""
        cleaned = line.replace("\u202f", " ").replace("\xa0", " ").strip()
        if not cleaned:
            return None, ""

        m = re.search(r"(\d[\d\s]*)(?:[,.](\d{1,2}))?\s*(?:€|EUR\b)", cleaned, re.IGNORECASE)
        if not m:
            m = re.search(r"(?:€|EUR)\s*(\d[\d\s]*)(?:[,.](\d{1,2}))?", cleaned, re.IGNORECASE)
        if m:
            whole = re.sub(r"\s+", "", m.group(1))
            dec = m.group(2) or "00"
            try:
                return round(float(f"{whole}.{dec}"), 2), "EUR"
            except ValueError:
                pass

        m_pln = re.search(r"(\d[\d\s]*)(?:[,.](\d{1,2}))?\s*(?:zł|zl|PLN)(?!\w)", cleaned, re.IGNORECASE)
        if not m_pln:
            m_pln = re.search(r"(?:PLN|zł|zl)\s*(\d[\d\s]*)(?:[,.](\d{1,2}))?", cleaned, re.IGNORECASE)
        if m_pln:
            whole = re.sub(r"\s+", "", m_pln.group(1))
            dec = m_pln.group(2) or "00"
            try:
                pln_val = float(f"{whole}.{dec}")
                return round(pln_val / PLN_TO_EUR_RATE, 2), "PLN"
            except ValueError:
                pass

        return None, ""

    @staticmethod
    def _resolve_cities(fb_city_setting: str) -> list[str]:
        raw = (fb_city_setting or "france").strip().lower()
        if raw in {"", "france", "toute la france", "all", "fr"}:
            return list(FRANCE_CITY_HUBS)
        cities = [
            re.sub(r"[^a-z0-9\-]", "", part.strip())
            for part in raw.split(",")
            if part.strip()
        ]
        return [c for c in cities if c] or list(FRANCE_CITY_HUBS)

    @staticmethod
    def _dismiss_popups(page: Any) -> None:
        cookie_labels = (
            "Autoriser tous les cookies",
            "Tout accepter",
            "Allow all cookies",
            "Refuser les cookies optionnels",
        )
        for txt in cookie_labels:
            for sel in (f'div[role="button"]:has-text("{txt}")', f'button:has-text("{txt}")'):
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=500):
                        btn.click(timeout=1200)
                        jitter_sleep(0.6, 1.2)
                        return
                except Exception:
                    pass

    @staticmethod
    def _extract_graphql_delivery(obj: Any, out: dict[str, dict[str, Any]]) -> None:
        """Extrait les infos delivery_types / shipping depuis les réponses GraphQL Facebook."""
        if isinstance(obj, dict):
            lid = obj.get("id")
            if lid and isinstance(lid, (str, int)) and str(lid).isdigit():
                dtypes = obj.get("delivery_types")
                if isinstance(dtypes, list):
                    ship_ok = any(
                        "SHIPPING" in str(dt).upper() or "DELIVERY" in str(dt).upper()
                        for dt in dtypes
                    )
                    out[str(lid)] = {
                        "delivery_types": [str(dt) for dt in dtypes],
                        "shipping_ok": ship_ok,
                    }
            for v in obj.values():
                if isinstance(v, (dict, list)):
                    FacebookScraper._extract_graphql_delivery(v, out)
        elif isinstance(obj, list):
            for el in obj:
                if isinstance(el, (dict, list)):
                    FacebookScraper._extract_graphql_delivery(el, out)

    @staticmethod
    def _looks_promising_title(title: str, price: float, settings: Settings) -> bool:
        if price < settings.min_price_eur or price > settings.max_price_eur:
            return False
        tn = normalize_text(title)
        has_cat = any(
            re.search(pat, tn)
            for pats in CATEGORY_KEYWORDS.values()
            for pat in pats
        )
        has_defect = any(re.search(pat, tn) for pat in DEFECT_SIGNALS)
        return has_cat and has_defect

    def _inspect_item_shipping(self, page: Any, item: RawListing) -> None:
        """Ouvre une page d'annonce FB pour lire la vraie description et vérifier la livraison."""
        try:
            page.goto(item.url, wait_until="domcontentloaded", timeout=20000)
            jitter_sleep(1.5, 2.5)
            main_el = page.locator('div[role="main"]').first
            raw_text = main_el.inner_text(timeout=4000) if main_el.count() > 0 else page.inner_text("body")
            norm = normalize_text(raw_text)

            # Extraire un extrait propre de la description pour l'IA
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
            desc_clean = " | ".join(lines[:18])[:1000]
            if desc_clean:
                item.description = desc_clean

            # Chercher un prix de livraison explicite ("Livraison · 5 €" ou "Frais de port : 6 €")
            ship_price_m = re.search(
                r"(?:livraison|exp[ée]dition|frais de port)[^\n\d]{0,20}(\d+(?:[,\.]\d{1,2})?)\s*€",
                raw_text,
                re.IGNORECASE,
            )
            if ship_price_m:
                item.shipping_price = float(ship_price_m.group(1).replace(",", "."))
                item.shipping_available = True
                item.shipping_note = f"{item.shipping_price:.2f} € (FB)"
                return

            if any(re.search(p, norm) for p in NO_SHIPPING_PATTERNS):
                item.shipping_available = False
                item.shipping_note = "Main propre uniquement (indiqué par le vendeur)"
                return

            if any(re.search(p, norm) for p in SHIPPING_OK_PATTERNS):
                item.shipping_available = True
                item.shipping_note = "Livraison / envoi mentionné dans l'annonce"
                return

            # Si aucune mention explicite de livraison ni de livraison FB native
            item.shipping_available = False
            item.shipping_note = "Livraison non confirmée (main propre par défaut sur FB)"
        except Exception as exc:
            logger.debug("Inspection detail FB ignoree pour %s: %s", item.external_id, exc)

    def _collect_cards(
        self,
        page: Any,
        url: str,
        query: str,
        city: str,
        used_shipping_filter: bool,
        gql_delivery: dict[str, dict[str, Any]],
        debug: bool,
    ) -> list[RawListing]:
        page.goto(url, wait_until="domcontentloaded", timeout=35000)
        self._dismiss_popups(page)
        try:
            page.wait_for_selector('a[href*="/marketplace/item/"]', timeout=10000)
        except Exception:
            pass
        jitter_sleep(2.0, 3.0)

        cur_url = page.url.lower()
        if "login" in cur_url or "checkpoint" in cur_url:
            raise ScraperBlockedError(
                r"Session Facebook expirée : relance '.venv\Scripts\python.exe run.py --fb-login'."
            )

        cards = page.locator('a[href*="/marketplace/item/"]').all()[:30]
        if debug:
            mode = "shipping" if used_shipping_filter else "standard"
            print(
                f"  [FB debug] ville={city} | mode={mode} | query='{query}' | cartes={len(cards)}"
            )

        if not cards:
            has_login_form = page.locator('input[name="email"], input[name="pass"]').count() > 0
            if has_login_form:
                raise ScraperBlockedError(
                    r"Non connecté à Facebook dans Chromium : relance '.venv\Scripts\python.exe run.py --fb-login'."
                )
            return []

        found: list[RawListing] = []
        for card in cards:
            try:
                href = card.get_attribute("href") or ""
                m = re.search(r"/marketplace/item/(\d+)", href)
                if not m:
                    continue
                item_id = m.group(1)
                text = card.inner_text().strip()
                lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
                if len(lines) < 2:
                    continue

                price = None
                currency = ""
                price_idx = -1
                for i, ln in enumerate(lines[:4]):
                    p_val, cur = self._parse_price(ln)
                    if p_val is not None:
                        price = p_val
                        currency = cur
                        price_idx = i
                        break
                if price is None:
                    continue

                fb_ui_junk = {
                    "liste des partenaires",
                    "sponsorise",
                    "sponsorisé",
                    "sponsored",
                    "expedition disponible",
                    "expédition disponible",
                    "livraison disponible",
                    "nouveau",
                    "baisse de prix",
                    "just listed",
                }
                remaining = [
                    ln
                    for i, ln in enumerate(lines)
                    if i != price_idx and ln.strip().lower() not in fb_ui_junk
                ]
                if not remaining:
                    continue
                title = remaining[0]
                location = remaining[1] if len(remaining) > 1 else city.capitalize()

                img_url = ""
                imgs = card.locator("img").all()
                if imgs:
                    img_url = imgs[0].get_attribute("src") or ""

                # Déterminer la livraison via le filtre FB ou les métadonnées GraphQL interceptées
                gql_info = gql_delivery.get(item_id)
                if used_shipping_filter:
                    ship_ok = True
                    ship_note = "Livraison FB activée"
                elif gql_info is not None:
                    ship_ok = bool(gql_info.get("shipping_ok"))
                    ship_note = (
                        "Livraison FB activée"
                        if ship_ok
                        else "Main propre uniquement (FB)"
                    )
                else:
                    ship_ok = False
                    ship_note = "Livraison à vérifier"

                cur_note = " (converti depuis PLN)" if currency == "PLN" else ""
                full_url = f"https://www.facebook.com/marketplace/item/{item_id}/"
                found.append(
                    RawListing(
                        site=self.name,
                        external_id=item_id,
                        title=title,
                        description=f"Annonce Facebook Marketplace ({query}) — {location}{cur_note}",
                        price=price,
                        url=full_url,
                        image_url=img_url,
                        location=location,
                        shipping_available=ship_ok,
                        shipping_price=None,
                        shipping_note=ship_note,
                    )
                )
            except Exception:
                continue
        return found

    def scan(self, settings: Settings, debug: bool = False) -> list[RawListing]:
        if not settings.enable_facebook:
            return []

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise ScraperBlockedError(
                "Playwright non installé (pip install playwright && playwright install chromium)"
            )

        if not FB_PROFILE_DIR.exists():
            raise ScraperBlockedError(
                r"Session FB absente : lance '.venv\Scripts\python.exe run.py --fb-login' une fois."
            )

        cities_pool = self._resolve_cities(getattr(settings, "fb_city", "france"))

        # Par cycle : 2 combinaisons (ville différente x requête différente) pour balayer toute la France en douceur
        pairs: list[tuple[str, str]] = []
        for _ in range(2):
            city = cities_pool[self._city_cursor % len(cities_pool)]
            query = FB_QUERIES[self._query_cursor % len(FB_QUERIES)]
            self._city_cursor = (self._city_cursor + 1) % len(cities_pool)
            self._query_cursor = (self._query_cursor + 1) % len(FB_QUERIES)
            pairs.append((city, query))

        results: dict[str, RawListing] = {}
        to_inspect_shipping: list[RawListing] = []

        with sync_playwright() as p:
            ctx = launch_stealth_context(p, FB_PROFILE_DIR, headless=True, use_system_channel=False)
            try:
                page = ctx.new_page()
                gql_delivery: dict[str, dict[str, Any]] = {}

                def on_response(resp: Any) -> None:
                    try:
                        if "graphql" in resp.url and resp.status == 200:
                            txt = resp.text()
                            if "delivery_types" in txt:
                                for chunk in txt.splitlines():
                                    chunk = chunk.strip()
                                    if chunk.startswith("{"):
                                        try:
                                            self._extract_graphql_delivery(json.loads(chunk), gql_delivery)
                                        except Exception:
                                            pass
                    except Exception:
                        pass

                import json  # local ref for callback
                page.on("response", on_response)

                for idx, (city, query) in enumerate(pairs):
                    if idx > 0:
                        jitter_sleep(3.5, 6.0)

                    base = f"https://www.facebook.com/marketplace/{city}/search/"
                    items: list[RawListing] = []

                    # 1. Si livraison obligatoire, on tente d'abord le filtre natif FB (deliveryMethod=shipping)
                    if settings.require_shipping:
                        ship_url = f"{base}?query={quote_plus(query)}&deliveryMethod=shipping&exact=false"
                        items = self._collect_cards(
                            page, ship_url, query, city, True, gql_delivery, debug
                        )

                    # 2. Fallback : si FB France renvoie 0 avec deliveryMethod=shipping, on scanne le pôle français
                    #    puis on inspecte la fiche des candidats prometteurs pour vérifier si le vendeur envoie
                    if not items:
                        std_url = f"{base}?query={quote_plus(query)}&exact=false"
                        items = self._collect_cards(
                            page, std_url, query, city, False, gql_delivery, debug
                        )
                        if settings.require_shipping:
                            for it in items:
                                if not it.shipping_available and self._looks_promising_title(
                                    it.title, it.price, settings
                                ):
                                    to_inspect_shipping.append(it)

                    for it in items:
                        results[it.external_id] = it

                # Vérifier jusqu'à 5 fiches prometteuses (description réelle + mention d'envoi/livraison)
                if settings.require_shipping and to_inspect_shipping:
                    for cand in to_inspect_shipping[:5]:
                        self._inspect_item_shipping(page, cand)
                        if debug:
                            print(
                                f"  [FB detail] '{cand.title[:40]}' -> ship={cand.shipping_available} ({cand.shipping_note})"
                            )
            finally:
                ctx.close()

        self._last_run_ts = time.time()
        return list(results.values())
