from __future__ import annotations

import re
import unicodedata
from abc import ABC, abstractmethod
from datetime import datetime

from bus_scrap.models import Location, SearchResult, TripOffer


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().lower()


def format_duration(hours: int | None = None, minutes: int | None = None) -> str:
    h = hours or 0
    m = minutes or 0
    if h and m:
        return f"{h}h {m:02d}min"
    if h:
        return f"{h}h"
    if m:
        return f"{m}min"
    return ""


def rank_location_name(query: str, candidate: str) -> tuple:
    needle = normalize(query)
    name = normalize(candidate)
    exact = name == needle or name.startswith(f"{needle},") or name.startswith(
        f"{needle} -"
    )
    starts = name.startswith(needle)
    contains = needle in name
    todos_boost = "todos" in name
    return (exact, starts, contains, todos_boost, -len(name))


class Provider(ABC):
    name: str
    aliases: tuple[str, ...] = ()

    @abstractmethod
    def search(
        self,
        origin_query: str,
        destination_query: str,
        travel_date: datetime,
    ) -> SearchResult:
        raise NotImplementedError


def sort_offers(offers: list[TripOffer]) -> list[TripOffer]:
    return sorted(offers, key=lambda offer: (offer.price, offer.departure or "", offer.company))
