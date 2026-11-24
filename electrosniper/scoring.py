"""
Algorithme de notation déterministe d'une affaire "HS à réparer puis revendre".

L'IA ne donne que des ESTIMATIONS factuelles (cote de revente, coût des pièces,
probabilité de réussir la réparation, valeur pour pièces si échec, liquidité...).
Toute la note est ensuite calculée ici, en Python, de façon reproductible :

1. Coût engagé       = prix + port d'achat
2. Revente nette     = cote fonctionnelle x 0.93 (négociation) - 4 € (emballage/frais)
3. Gain si réussite  = revente nette - coût engagé - pièces
4. Résultat si échec = valeur pour pièces - coût engagé - 50 % des pièces (achetées avant de constater l'échec)
5. Espérance (EV)    = p x gain si réussite + (1 - p) x résultat si échec
6. Note /100         = moyenne géométrique pondérée de 5 critères (EV, rentabilité, chance de
                       réussite, liquidité, facilité), puis ajustée par la confiance dans
                       l'annonce et plafonnée par des garde-fous durs.

La moyenne géométrique fait qu'un seul critère catastrophique (marge nulle, réparation
quasi impossible, objet invendable) tire toute la note vers le bas : impossible d'avoir
85/100 sur une affaire non rentable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SCORE_VERSION = 2

RESALE_NEGOTIATION = 0.93  # on vend en moyenne ~7 % sous le prix affiché
RESALE_FIXED_COSTS = 4.0  # emballage, scotch, déplacement point relais
PARTS_SPENT_ON_FAILURE = 0.5  # part des pièces déjà achetées quand on constate l'échec
MIN_TARGET_PROFIT = 15.0  # bénéfice espéré minimum visé pour le prix max conseillé
MIN_TARGET_ROI = 0.30  # rentabilité minimum visée pour le prix max conseillé

# Poids de la moyenne géométrique (somme = 1)
W_PROFIT = 0.32
W_ROI = 0.18
W_SUCCESS = 0.25
W_LIQUIDITY = 0.15
W_EASE = 0.10

DEFAULT_SHIPPING_EUR = 6.0


@dataclass
class DealInputs:
    buy_price: float
    ship_cost: float
    resale_working_eur: float
    parts_cost_eur: float
    success_probability: float  # 0..1
    salvage_value_eur: float
    liquidity: int  # 1..10
    repair_ease: int  # 1..10
    confidence: int  # 1..10
    is_relevant_device: bool = True
    is_actually_defective: bool = True
    already_opened: bool = False


@dataclass
class DealScore:
    score: int
    repair_score: int
    resale_score: int
    margin_score: int
    expected_profit_eur: float
    profit_if_success_eur: float
    max_loss_eur: float
    total_cost_eur: float
    roi: float
    max_buy_price_eur: float
    success_pct: int
    caps: list[str]


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _to_int(v: object, default: int, lo: int, hi: int) -> int:
    try:
        return int(_clamp(int(round(float(v))), lo, hi))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _to_float(v: object, default: float = 0.0) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default


def saturate(x: float, scale: float) -> float:
    """0 -> 0, scale -> 0.63, 2*scale -> 0.86, 3*scale -> 0.95."""
    if x <= 0:
        return 0.0
    return 1.0 - math.exp(-x / scale)


def compute_deal_score(inp: DealInputs) -> DealScore:
    buy = max(0.0, _to_float(inp.buy_price))
    ship = max(0.0, _to_float(inp.ship_cost, DEFAULT_SHIPPING_EUR))
    resale = max(0.0, _to_float(inp.resale_working_eur))
    parts = max(0.0, _to_float(inp.parts_cost_eur))
    p = _clamp(_to_float(inp.success_probability, 0.5), 0.03, 0.97)
    liquidity = _to_int(inp.liquidity, 5, 1, 10)
    ease = _to_int(inp.repair_ease, 5, 1, 10)
    conf = _to_int(inp.confidence, 5, 1, 10)

    if not inp.is_actually_defective:
        # Objet fonctionnel : rien à réparer, c'est de l'achat-revente pur
        p = 0.97
        parts = 0.0

    # Valeur pour pièces : jamais plus de 60 % de la cote fonctionnelle
    salvage = _clamp(_to_float(inp.salvage_value_eur), 0.0, 0.6 * resale)

    total_cost = buy + ship
    resale_net = max(0.0, resale * RESALE_NEGOTIATION - RESALE_FIXED_COSTS)
    profit_success = resale_net - total_cost - parts
    outcome_failure = salvage - total_cost - parts * PARTS_SPENT_ON_FAILURE
    ev = p * profit_success + (1 - p) * outcome_failure
    invested = max(15.0, total_cost + parts)
    roi = ev / invested
    max_loss = max(0.0, -outcome_failure)

    # Prix d'achat max conseillé (hors port) pour viser EV >= 15 € et ROI >= 30 %.
    # EV(c) = K - c avec c = coût engagé (prix + port).
    k = p * (resale_net - parts) + (1 - p) * (salvage - parts * PARTS_SPENT_ON_FAILURE)
    c_max = min((k - MIN_TARGET_ROI * parts) / (1 + MIN_TARGET_ROI), k - MIN_TARGET_PROFIT)
    max_buy = max(0.0, c_max - ship)

    # --- Critères normalisés 0..1 ---
    c_profit = saturate(ev, 45.0)
    c_roi = saturate(roi, 0.5)
    c_success = p
    c_liq = liquidity / 10.0
    c_ease = ease / 10.0

    floor = 0.02
    log_sum = (
        W_PROFIT * math.log(max(floor, c_profit))
        + W_ROI * math.log(max(floor, c_roi))
        + W_SUCCESS * math.log(max(floor, c_success))
        + W_LIQUIDITY * math.log(max(floor, c_liq))
        + W_EASE * math.log(max(floor, c_ease))
    )
    score = 100.0 * math.exp(log_sum)

    # Confiance : annonce vague / photo absente / panne floue = plus de risque
    score *= 0.85 + 0.15 * (conf / 10.0)

    caps: list[str] = []
    if inp.already_opened:
        score *= 0.88
        caps.append("Déjà ouvert / bricolé (-12 %)")

    # "Trop beau pour être vrai" : gain > 5x la mise -> on se méfie (arnaque, mauvaise lecture)
    if total_cost >= 15 and profit_success > 5 * total_cost:
        score *= 0.90
        caps.append("Gain potentiel suspect (> 5x la mise)")

    # --- Garde-fous durs ---
    def cap(limit: float, reason: str) -> None:
        nonlocal score
        if score > limit:
            score = limit
            caps.append(reason)

    if ev <= 0:
        cap(20, "Espérance de gain négative")
    elif ev < 10:
        cap(35, "Espérance de gain < 10 €")
    elif ev < 20:
        cap(55, "Espérance de gain < 20 €")
    if p < 0.25:
        cap(40, "Réparation très incertaine (< 25 %)")
    if not inp.is_actually_defective:
        cap(30, "Objet non défectueux")
    if not inp.is_relevant_device:
        cap(5, "Pas un appareil réparable (accessoire / hors sujet)")

    final = int(round(_clamp(score, 0, 100)))

    margin_score = int(round(10 * math.sqrt(c_profit * c_roi)))
    repair_score = int(round(_clamp(10 * (0.6 * p + 0.4 * c_ease), 1, 10)))
    if not inp.is_relevant_device:
        repair_score = 1

    return DealScore(
        score=final,
        repair_score=repair_score,
        resale_score=liquidity,
        margin_score=int(_clamp(margin_score, 0, 10)),
        expected_profit_eur=round(ev, 2),
        profit_if_success_eur=round(profit_success, 2),
        max_loss_eur=round(max_loss, 2),
        total_cost_eur=round(total_cost + parts, 2),
        roi=round(roi, 3),
        max_buy_price_eur=round(max_buy, 0),
        success_pct=int(round(p * 100)),
        caps=caps,
    )
