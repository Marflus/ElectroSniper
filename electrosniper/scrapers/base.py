from __future__ import annotations

from abc import ABC, abstractmethod

from electrosniper.config import Settings
from electrosniper.models import RawListing


class ScraperBlockedError(Exception):
    """Levée lorsqu'un site bloque temporairement les requêtes (403/429/DataDome)."""


class BaseScraper(ABC):
    name: str = "base"

    @abstractmethod
    def scan(self, settings: Settings) -> list[RawListing]:
        """Retourne un lot d'annonces brutes récentes."""
