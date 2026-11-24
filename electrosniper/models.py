from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RawListing:
    site: str
    external_id: str
    title: str
    description: str
    price: float
    url: str
    image_url: str = ""
    location: str = ""
    published_at: str = ""
    shipping_available: bool = False
    shipping_price: float | None = None
    shipping_note: str = ""
    raw_category: str = ""
    condition_label: str = ""
    seller_name: str = ""


@dataclass
class FilterResult:
    accepted: bool
    category: str = "autre"
    reject_reason: str = ""
    already_opened: bool = False
    opened_reason: str = ""


@dataclass
class TriageResult:
    score: int
    repair_score: int
    resale_score: int
    margin_score: int
    estimated_resale_eur: float
    estimated_parts_eur: float
    estimated_profit_eur: float
    suspected_fault: str
    verdict: str  # "GO" | "A_VOIR" | "PASS"
    reasoning: str
    model: str


@dataclass
class DeepAnalysisResult:
    verdict: str  # "ACHETER" | "NEGOCIER" | "LAISSER_TOMBER"
    score: int
    repair_score: int
    resale_score: int
    margin_score: int
    recommended_max_buy_eur: float
    market_price_low_eur: float
    market_price_high_eur: float
    estimated_resale_eur: float
    estimated_parts_eur: float
    estimated_repair_time: str
    estimated_net_profit_eur: float
    resale_speed: str
    suspected_fault: str = ""
    probable_faults: list[dict[str, Any]] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    questions_for_seller: list[str] = field(default_factory=list)
    seller_message_template: str = ""
    summary: str = ""
    model: str = ""
