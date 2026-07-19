from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Location:
    id: str
    name: str
    slug: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class TripOffer:
    site: str
    price: float
    currency: str = "BRL"
    departure: str = ""
    arrival: str = ""
    duration: str = ""
    seat_type: str = ""
    company: str = ""
    status: str = "available"
    seats_available: int | None = None
    price_with_fee: float | None = None
    uid: str = ""
    booking_url: str = ""
    notes: str = ""


@dataclass
class SearchResult:
    site: str
    origin: Location
    destination: Location
    travel_date: datetime
    offers: list[TripOffer]
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "site": self.site,
            "origem": {
                "id": self.origin.id,
                "name": self.origin.name,
                "slug": self.origin.slug,
                **self.origin.meta,
            },
            "destino": {
                "id": self.destination.id,
                "name": self.destination.name,
                "slug": self.destination.slug,
                **self.destination.meta,
            },
            "data": self.travel_date.strftime("%d/%m/%Y"),
            "moeda": "BRL",
            "quantidade": len(self.offers),
            "avisos": self.warnings,
            "passagens": [asdict(offer) for offer in self.offers],
        }
