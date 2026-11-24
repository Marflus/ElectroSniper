from __future__ import annotations

import json
import logging
import re
from typing import Any

from anthropic import Anthropic

from electrosniper.config import Settings
from electrosniper.db import Database
from electrosniper.models import DeepAnalysisResult, TriageResult

logger = logging.getLogger(__name__)

MODEL_PRICING_PER_M: dict[str, tuple[float, float]] = {
    "haiku": (0.80, 4.00),
    "sonnet": (3.00, 15.00),
    "opus": (15.00, 75.00),
}

TRIAGE_FALLBACKS = ["claude-haiku-4-5-20251001", "claude-haiku-4-5", "claude-3-5-haiku-latest"]
DEEP_FALLBACKS = ["claude-sonnet-4-5-20250929", "claude-sonnet-4-5", "claude-3-7-sonnet-latest"]


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    low = model.lower()
    in_rate, out_rate = MODEL_PRICING_PER_M["sonnet"]
    if "haiku" in low:
        in_rate, out_rate = MODEL_PRICING_PER_M["haiku"]
    elif "opus" in low:
        in_rate, out_rate = MODEL_PRICING_PER_M["opus"]
    return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000.0


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start : end + 1]
    return json.loads(text)


def compute_reliable_scores(
    *,
    buy_price: float,
    ship_cost: float,
    est_resale: float,
    est_parts: float,
    raw_repair_score: int,
    raw_resale_score: int,
    is_relevant_device: bool,
    is_actually_defective: bool,
    already_opened: bool,
) -> tuple[int, int, int, int, float]:
    """
    Calcule de façon déterministe et fiable :
    (score_global_100, repair_score_10, resale_score_10, margin_score_10, est_profit_eur).
    Empêche toute note incohérente (ex: 85/100 sur une marge négative ou sur une sacoche).
    """
    est_resale = max(0.0, float(est_resale))
    est_parts = max(0.0, float(est_parts))
    total_cost = max(0.0, float(buy_price) + float(ship_cost) + est_parts)
    est_profit = round(est_resale - total_cost, 2)
    roi = est_profit / max(20.0, total_cost)

    repair = max(1, min(10, int(raw_repair_score)))
    resale = max(1, min(10, int(raw_resale_score)))

    # 1. Calcul strictement mathématique de la note de marge (0..10)
    if est_profit <= 0:
        margin = 0
    elif est_profit < 10:
        margin = 1
    elif est_profit < 20:
        margin = 3 if roi >= 0.40 else 2
    elif est_profit < 30:
        margin = 4
    elif est_profit < 45:
        margin = 6
    elif est_profit < 70:
        margin = 7
    elif est_profit < 100:
        margin = 8
    elif est_profit < 150:
        margin = 9
    else:
        margin = 10

    # Ajustement selon le ROI (immobiliser 400€ pour gagner 35€ est peu intéressant)
    if est_profit > 0:
        if roi < 0.15:
            margin = min(margin, 4)
        elif roi < 0.25:
            margin = min(margin, 6)
        elif roi >= 0.65 and est_profit >= 30:
            margin = min(10, margin + 1)

    # 2. Garde-fous pertinence / panne réelle
    if not is_relevant_device:
        repair = 1
        margin = min(margin, 2)
        score = min(15, round((0.5 * margin + 0.25 * repair + 0.25 * resale) * 5))
        return max(0, score), repair, resale, margin, est_profit

    if not is_actually_defective:
        # Ne jamais récompenser d'un 10/10 en réparation un article fonctionnel !
        repair = min(repair, 2)

    # 3. Note globale pondérée : Marge 45%, Réparabilité 30%, Revente 25%
    weighted = round((0.45 * margin + 0.30 * repair + 0.25 * resale) * 10)

    if already_opened:
        weighted = max(0, weighted - 10)

    # 4. Plafonds durs selon la rentabilité réelle
    if est_profit <= 0:
        weighted = min(weighted, 22)
    elif est_profit < 10:
        weighted = min(weighted, 38)
    elif est_profit < 20:
        weighted = min(weighted, 52)
    elif est_profit < 30:
        weighted = min(weighted, 65)

    # Plafond si ce n'est pas réellement un objet HS à réparer
    if not is_actually_defective:
        weighted = min(weighted, 30 if est_profit < 40 else 48)

    return max(0, min(100, int(weighted))), repair, resale, margin, est_profit


class AIAnalyzer:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _client(self, settings: Settings) -> Anthropic:
        if not settings.anthropic_api_key:
            raise RuntimeError("Clé ANTHROPIC_API_KEY manquante ou invalide dans .env")
        return Anthropic(api_key=settings.anthropic_api_key)

    def _call_with_fallback(
        self,
        client: Anthropic,
        preferred_model: str,
        fallbacks: list[str],
        *,
        max_tokens: int,
        system: str,
        user_prompt: str,
    ) -> tuple[Any, str]:
        candidates = [preferred_model] + [m for m in fallbacks if m != preferred_model]
        last_exc: Exception | None = None
        for model in candidates:
            try:
                msg = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                return msg, model
            except Exception as exc:
                last_exc = exc
                err_txt = str(exc).lower()
                if "not_found" in err_txt or ("model" in err_txt and "404" in err_txt):
                    logger.warning("Modèle Anthropic %s indisponible, essai du suivant...", model)
                    continue
                raise
        raise last_exc or RuntimeError("Aucun modèle Anthropic disponible")

    @staticmethod
    def _ship_cost(listing: dict[str, Any]) -> float:
        if listing.get("shipping_price") is not None:
            return float(listing["shipping_price"])
        return 6.0

    def triage_listing(self, listing: dict[str, Any], settings: Settings) -> TriageResult:
        client = self._client(settings)

        shipping_str = (
            f"{listing['shipping_price']:.2f} €"
            if listing.get("shipping_price") is not None
            else (listing.get("shipping_note") or "Livraison dispo (~6 € estimé)")
        )
        opened_flag = (
            f"ATTENTION : signal 'déjà ouvert / bricolé' ({listing.get('opened_reason')})"
            if listing.get("already_opened")
            else "Non signalé comme déjà ouvert."
        )

        system_prompt = (
            "Tu es un technicien sévère et réaliste spécialisé en réparation électronique "
            "(consoles, PC, outillage électroportatif, audio, photo, petit électroménager, tablettes) "
            "et en achat-revente en France (prix réels Leboncoin/Vinted). "
            "RÈGLES STRICTES : "
            "1) Si l'annonce est un accessoire (sacoche, câble, batterie seule, jeu, boîte, coque) ou hors sujet, "
            "mets is_relevant_device=false et repair_score=1. "
            "2) Si l'objet n'est PAS défectueux / en panne / pour pièces, mets is_actually_defective=false et "
            "repair_score=1 (NE METS JAMAIS 10/10 en réparation sous prétexte qu'il n'y a rien à réparer). "
            "3) Sois CONSERVATEUR sur estimated_resale_eur (prix auquel ça se vend vraiment en 7 jours en France) "
            "et réaliste sur estimated_parts_eur (coût pièces + consommables). "
            "Réponds UNIQUEMENT par un JSON valide sans texte autour."
        )

        user_prompt = f"""Évalue cette annonce de matériel HS / à réparer :
- Site : {listing['site']}
- Catégorie : {listing['category']}
- Titre : {listing['title']}
- Prix affiché : {listing['price']} €
- Livraison : {shipping_str}
- Localisation : {listing.get('location') or 'NC'}
- Alerte ouverture : {opened_flag}
- Description : {(listing.get('description') or 'Aucune description')[:1200]}

Renvoie STRICTEMENT ce JSON :
{{
  "is_relevant_device": <bool : true uniquement si appareil électronique/outil réparable, false si sacoche/câble/batterie seule/accessoire/jeu>,
  "is_actually_defective": <bool : true uniquement si réellement en panne/HS/pour pièces/non testé>,
  "repair_score": <int 1..10 : facilité réelle de réparation et dispo pièces ; mets 1 si pas de panne ou non réparable>,
  "resale_score": <int 1..10 : demande et rapidité de revente en France une fois réparé>,
  "estimated_resale_eur": <float : prix de revente réaliste et conservateur une fois réparé>,
  "estimated_parts_eur": <float : coût probable des pièces de rechange>,
  "suspected_fault": "<max 90 caractères : panne probable la plus crédible>",
  "reasoning": "<max 180 caractères : justification franche et réaliste>"
}}"""

        msg, used_model = self._call_with_fallback(
            client,
            settings.anthropic_triage_model,
            TRIAGE_FALLBACKS,
            max_tokens=340,
            system=system_prompt,
            user_prompt=user_prompt,
        )

        in_tok = getattr(msg.usage, "input_tokens", 0)
        out_tok = getattr(msg.usage, "output_tokens", 0)
        self.db.log_api_usage(
            used_model, "triage", in_tok, out_tok, estimate_cost_usd(used_model, in_tok, out_tok)
        )

        raw_text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        data = extract_json(raw_text)

        is_rel = bool(data.get("is_relevant_device", True))
        is_def = bool(data.get("is_actually_defective", True))
        est_resale = max(0.0, float(data.get("estimated_resale_eur", 0.0)))
        est_parts = max(0.0, float(data.get("estimated_parts_eur", 0.0)))

        score, repair, resale, margin, est_profit = compute_reliable_scores(
            buy_price=float(listing["price"]),
            ship_cost=self._ship_cost(listing),
            est_resale=est_resale,
            est_parts=est_parts,
            raw_repair_score=int(data.get("repair_score", 5)),
            raw_resale_score=int(data.get("resale_score", 5)),
            is_relevant_device=is_rel,
            is_actually_defective=is_def,
            already_opened=bool(listing.get("already_opened")),
        )

        if (
            is_rel
            and is_def
            and score >= settings.min_alert_score
            and repair >= 5
            and est_profit >= settings.min_alert_profit_eur
        ):
            verdict = "GO"
        elif is_rel and is_def and score >= 58 and est_profit >= 20:
            verdict = "A_VOIR"
        else:
            verdict = "PASS"

        return TriageResult(
            score=score,
            repair_score=repair,
            resale_score=resale,
            margin_score=margin,
            estimated_resale_eur=round(est_resale, 2),
            estimated_parts_eur=round(est_parts, 2),
            estimated_profit_eur=est_profit,
            suspected_fault=str(data.get("suspected_fault") or "Non déterminée")[:140],
            verdict=verdict,
            reasoning=str(data.get("reasoning") or "")[:300],
            model=used_model,
        )

    def deep_analyze_listing(self, listing: dict[str, Any], settings: Settings) -> DeepAnalysisResult:
        client = self._client(settings)

        shipping_str = (
            f"{listing['shipping_price']:.2f} €"
            if listing.get("shipping_price") is not None
            else (listing.get("shipping_note") or "Livraison dispo (~6 € estimé)")
        )

        system_prompt = (
            "Tu es un expert senior en diagnostic électronique et en achat-revente de matériel réparé "
            "en France (Leboncoin, Vinted, eBay FR). Tu fais des analyses exigeantes, techniques et sans complaisance. "
            "Prends en compte les pannes connues du modèle exact, la disponibilité et le coût réel des pièces "
            "(AliExpress, SOSav, OEM), le risque de carte mère irréparable ou de blocage compte "
            "(iCloud, console bannie, batterie BMS verrouillée). "
            "Si l'objet n'est pas un appareil électronique réparable (sacoche, câble, batterie seule, jeu) "
            "ou n'est pas en panne, signale-le via is_relevant_device / is_actually_defective et verdict LAISSER_TOMBER. "
            "Réponds UNIQUEMENT par un objet JSON valide."
        )

        user_prompt = f"""Réalise une analyse approfondie et recalibre la note de cette annonce :
- Site : {listing['site']}
- Catégorie : {listing['category']}
- Titre : {listing['title']}
- Prix affiché : {listing['price']} €
- Livraison : {shipping_str}
- Localisation : {listing.get('location') or 'NC'}
- Déjà ouvert détecté : {bool(listing.get('already_opened'))} ({listing.get('opened_reason') or 'non'})
- Pré-analyse rapide : score {listing.get('ai_score')}/100 | panne suspectée : {listing.get('suspected_fault')}
- Description complète :
{(listing.get('description') or 'Aucune description')[:2500]}

Renvoie STRICTEMENT ce JSON :
{{
  "is_relevant_device": <bool : true uniquement si appareil électronique/outil réparable>,
  "is_actually_defective": <bool : true uniquement si réellement en panne/HS/pour pièces/non testé>,
  "verdict": "ACHETER" | "NEGOCIER" | "LAISSER_TOMBER",
  "repair_score": <int 1..10 : facilité réelle de réparation ; 1 si pas de panne ou irréparable>,
  "resale_score": <int 1..10 : liquidité / facilité de revente en France>,
  "recommended_max_buy_eur": <float : prix d'achat max conseillé hors port pour garder au moins 30% de marge>,
  "market_price_low_eur": <float : fourchette basse occasion fonctionnel en France>,
  "market_price_high_eur": <float : fourchette haute occasion fonctionnel en France>,
  "estimated_parts_eur": <float : budget pièces réaliste>,
  "estimated_repair_time": "<ex: 30-45 min ou 1h30>",
  "resale_speed": "<ex: Très rapide (2-5 jours), Moyenne (1-2 semaines), Lente>",
  "suspected_fault": "<max 90 caractères : panne probable principale>",
  "probable_faults": [
    {{"fault": "<nom technique précis>", "probability": <int 0..100>, "fix": "<réparation concrète & difficulté>"}}
  ],
  "red_flags": ["<risque concret 1>", "<risque concret 2>"],
  "questions_for_seller": ["<question précise 1>", "<question précise 2>", "<question précise 3>"],
  "seller_message_template": "<message court, poli et naturel à copier-coller au vendeur>",
  "summary": "<synthèse claire en 3-4 phrases sur l'intérêt réel de l'affaire>"
}}"""

        msg, used_model = self._call_with_fallback(
            client,
            settings.anthropic_deep_model,
            DEEP_FALLBACKS,
            max_tokens=1150,
            system=system_prompt,
            user_prompt=user_prompt,
        )

        in_tok = getattr(msg.usage, "input_tokens", 0)
        out_tok = getattr(msg.usage, "output_tokens", 0)
        self.db.log_api_usage(
            used_model, "deep_analysis", in_tok, out_tok, estimate_cost_usd(used_model, in_tok, out_tok)
        )

        raw_text = "".join(block.text for block in msg.content if hasattr(block, "text"))
        data = extract_json(raw_text)

        is_rel = bool(data.get("is_relevant_device", True))
        is_def = bool(data.get("is_actually_defective", True))
        low_eur = max(0.0, float(data.get("market_price_low_eur", 0.0)))
        high_eur = max(low_eur, float(data.get("market_price_high_eur", low_eur)))
        # Prix de revente conservateur (60% borne basse + 40% borne haute)
        est_resale = round(0.6 * low_eur + 0.4 * high_eur, 2)
        est_parts = max(0.0, float(data.get("estimated_parts_eur", 0.0)))

        score, repair, resale, margin, est_profit = compute_reliable_scores(
            buy_price=float(listing["price"]),
            ship_cost=self._ship_cost(listing),
            est_resale=est_resale,
            est_parts=est_parts,
            raw_repair_score=int(data.get("repair_score", 5)),
            raw_resale_score=int(data.get("resale_score", 5)),
            is_relevant_device=is_rel,
            is_actually_defective=is_def,
            already_opened=bool(listing.get("already_opened")),
        )

        verdict = str(data.get("verdict") or "NEGOCIER").upper()
        if verdict not in {"ACHETER", "NEGOCIER", "LAISSER_TOMBER"}:
            verdict = "NEGOCIER"
        # Cohérence verdict vs rentabilité réelle
        if not is_rel or not is_def or est_profit <= 0 or score < 35:
            verdict = "LAISSER_TOMBER"
        elif verdict == "ACHETER" and (est_profit < 20 or score < 62):
            verdict = "NEGOCIER"

        probable_faults = list(data.get("probable_faults") or [])
        main_fault = str(data.get("suspected_fault") or "").strip()
        if not main_fault and probable_faults and isinstance(probable_faults[0], dict):
            main_fault = str(probable_faults[0].get("fault") or "")
        if not main_fault:
            main_fault = str(listing.get("suspected_fault") or "Non déterminée")

        return DeepAnalysisResult(
            verdict=verdict,
            score=score,
            repair_score=repair,
            resale_score=resale,
            margin_score=margin,
            recommended_max_buy_eur=round(max(0.0, float(data.get("recommended_max_buy_eur", 0.0))), 2),
            market_price_low_eur=round(low_eur, 2),
            market_price_high_eur=round(high_eur, 2),
            estimated_resale_eur=est_resale,
            estimated_parts_eur=round(est_parts, 2),
            estimated_repair_time=str(data.get("estimated_repair_time") or "NC"),
            estimated_net_profit_eur=est_profit,
            resale_speed=str(data.get("resale_speed") or "NC"),
            suspected_fault=main_fault[:140],
            probable_faults=probable_faults,
            red_flags=list(data.get("red_flags") or []),
            questions_for_seller=list(data.get("questions_for_seller") or []),
            seller_message_template=str(data.get("seller_message_template") or ""),
            summary=str(data.get("summary") or ""),
            model=used_model,
        )
