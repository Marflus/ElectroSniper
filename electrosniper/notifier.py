from __future__ import annotations

import html
import logging
from typing import Any

import httpx

from electrosniper.config import Settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def is_configured(self, settings: Settings) -> bool:
        return bool(settings.telegram_bot_token and settings.telegram_chat_id)

    def send_test(self, settings: Settings) -> tuple[bool, str]:
        if not self.is_configured(settings):
            return False, "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID non renseigné dans .env"

        text = (
            "<b>ElectroSniper — Connexion active</b>\n"
            f"Seuil d'alerte : <b>{settings.min_alert_score}/100</b> "
            f"(marge min. <b>{settings.min_alert_profit_eur:.0f} EUR</b>)\n"
            f"Dashboard : http://{settings.web_host}:{settings.web_port}"
        )
        return self._send_message(settings, text)

    def send_deal_alert(self, listing: dict[str, Any], settings: Settings) -> bool:
        if not self.is_configured(settings):
            return False

        title = html.escape(str(listing.get("title") or ""))
        site = html.escape(str(listing.get("site") or "").upper())
        cat = html.escape(str(listing.get("category") or "").replace("_", " "))
        fault = html.escape(str(listing.get("suspected_fault") or "Non déterminée"))
        reason = html.escape(str(listing.get("ai_reasoning") or ""))
        ship_txt = (
            f"{listing['shipping_price']:.2f} €"
            if listing.get("shipping_price") is not None
            else html.escape(str(listing.get("shipping_note") or "Livraison dispo"))
        )
        opened_line = (
            f"\n<b>Alerte ouverture :</b> {html.escape(str(listing.get('opened_reason') or 'Déjà ouvert'))}"
            if listing.get("already_opened")
            else ""
        )

        caption = (
            f"<b>SCORE {listing.get('ai_score', 0)}/100</b>  |  <i>{site} · {cat}</i>\n"
            f"<b>{title}</b>\n\n"
            f"Prix : <b>{listing['price']:.0f} €</b>  |  Port : {ship_txt}\n"
            f"Marge nette est. : <b>+{listing.get('estimated_profit_eur', 0):.0f} €</b> "
            f"(revente ~{listing.get('estimated_resale_eur', 0):.0f} € · pièces ~{listing.get('estimated_parts_eur', 0):.0f} €)\n"
            f"Réparabilité {listing.get('repair_score', 0)}/10 · "
            f"Revente {listing.get('resale_score', 0)}/10 · "
            f"Marge {listing.get('margin_score', 0)}/10\n"
            f"Panne probable : {fault}\n"
            f"Analyse : {reason}{opened_line}\n\n"
            f"<a href=\"{html.escape(listing['url'])}\">Voir l'annonce</a>  |  "
            f"<a href=\"http://{settings.web_host}:{settings.web_port}/?open={listing['id']}\">Analyse approfondie</a>"
        )

        image_url = str(listing.get("image_url") or "")
        if image_url.startswith("http"):
            ok, _ = self._send_photo(settings, image_url, caption)
            if ok:
                return True

        ok, _ = self._send_message(settings, caption)
        return ok

    def _send_photo(self, settings: Settings, photo_url: str, caption: str) -> tuple[bool, str]:
        api = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendPhoto"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    api,
                    data={
                        "chat_id": settings.telegram_chat_id,
                        "photo": photo_url,
                        "caption": caption[:1020],
                        "parse_mode": "HTML",
                    },
                )
            if resp.status_code == 200:
                return True, "OK"
            return False, resp.text
        except Exception as exc:
            logger.warning("Erreur Telegram sendPhoto: %s", exc)
            return False, str(exc)

    def _send_message(self, settings: Settings, text: str) -> tuple[bool, str]:
        api = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        try:
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(
                    api,
                    data={
                        "chat_id": settings.telegram_chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": False,
                    },
                )
            if resp.status_code == 200:
                return True, "OK"
            return False, resp.text
        except Exception as exc:
            logger.warning("Erreur Telegram sendMessage: %s", exc)
            return False, str(exc)
