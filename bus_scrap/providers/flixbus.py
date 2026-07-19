from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from bus_scrap.http_util import http_get, http_get_json
from bus_scrap.models import Location, SearchResult, TripOffer
from bus_scrap.providers.base import Provider, format_duration, normalize, sort_offers

AUTOCOMPLETE_URL = "https://global.api.flixbus.com/search/autocomplete/cities"
SEARCH_URL = "https://global.api.flixbus.com/search/service/v4/search"
SHOP_URL = "https://shop.flixbus.com.br/search"
FALLBACK_PARTNER_KEY = "X7M2Z4Q9A5F8L1K3W6T0B9Y2H8R3N6C1"


class FlixBusProvider(Provider):
    name = "flixbus"
    aliases = ("flixbus.com.br", "flix")

    def search(
        self,
        origin_query: str,
        destination_query: str,
        travel_date: datetime,
    ) -> SearchResult:
        partner_key = self._fetch_partner_key()
        origin = self._resolve_city(origin_query, partner_key)
        destination = self._resolve_city(destination_query, partner_key)
        offers = self._search_trips(origin, destination, travel_date, partner_key)

        warnings: list[str] = []
        if not origin.meta.get("is_flixbus_city"):
            warnings.append(f"Origem sem operação FlixBus direta: {origin.name}")
        if not destination.meta.get("is_flixbus_city"):
            warnings.append(f"Destino sem operação FlixBus direta: {destination.name}")

        return SearchResult(
            site=self.name,
            origin=origin,
            destination=destination,
            travel_date=travel_date,
            offers=offers,
            warnings=warnings,
        )

    def _fetch_partner_key(self) -> str:
        sample = (
            f"{SHOP_URL}?departureCity=af4f8ad0-0d75-4925-9f64-fff8bb0e2e62"
            "&arrivalCity=9fef3da1-ac4e-4340-a36c-c177c0128f66"
            "&rideDate=20.07.2026&adult=1&currency=BRL"
        )
        try:
            html = http_get(sample)
            match = re.search(r'"partnerAuthKey"\s*:\s*"([^"]+)"', html)
            if match:
                return match.group(1)
        except RuntimeError:
            pass
        return FALLBACK_PARTNER_KEY

    def _api_get(self, url: str, partner_key: str) -> Any:
        return http_get_json(
            url,
            headers={"X-API-KEY": partner_key, "Accept": "application/json"},
        )

    def _resolve_city(self, query: str, partner_key: str) -> Location:
        params = urlencode({"q": query, "locale": "pt_BR"})
        results = self._api_get(f"{AUTOCOMPLETE_URL}?{params}", partner_key)
        if not isinstance(results, list) or not results:
            raise ValueError(f"FlixBus: nenhuma cidade encontrada para '{query}'.")

        needle = normalize(query)

        def rank(item: dict[str, Any]) -> tuple:
            name = normalize(str(item.get("name", "")))
            country = str(item.get("country", "")).lower()
            exact = name == needle or name.startswith(f"{needle},")
            starts = name.startswith(needle)
            contains = needle in name
            return (
                exact,
                starts,
                contains,
                country == "br",
                bool(item.get("is_flixbus_city")),
                float(item.get("score") or 0),
            )

        best = max(results, key=rank)
        city_id = best.get("id")
        if not city_id:
            raise ValueError(f"FlixBus: cidade '{query}' sem id válido.")

        return Location(
            id=str(city_id),
            name=str(best.get("name") or query),
            slug=str(best.get("slug") or ""),
            meta={
                "country": str(best.get("country") or "").upper(),
                "is_flixbus_city": bool(best.get("is_flixbus_city")),
                "legacy_id": best.get("legacy_id"),
            },
        )

    def _search_trips(
        self,
        origin: Location,
        destination: Location,
        travel_date: datetime,
        partner_key: str,
    ) -> list[TripOffer]:
        ride_date_api = travel_date.strftime("%d.%m.%Y")
        params = urlencode(
            {
                "from_city_id": origin.id,
                "to_city_id": destination.id,
                "departure_date": ride_date_api,
                "products": json.dumps({"adult": 1}, separators=(",", ":")),
                "currency": "BRL",
                "locale": "pt_BR",
                "search_by": "cities",
                "include_after_midnight_rides": 0,
            }
        )
        payload = self._api_get(f"{SEARCH_URL}?{params}", partner_key)
        booking_url = (
            f"{SHOP_URL}?"
            + urlencode(
                {
                    "departureCity": origin.id,
                    "arrivalCity": destination.id,
                    "rideDate": ride_date_api,
                    "adult": 1,
                    "currency": "BRL",
                }
            )
        )

        offers: list[TripOffer] = []
        for trip_group in payload.get("trips") or []:
            results = trip_group.get("results") or {}
            items = results.values() if isinstance(results, dict) else results
            for item in items:
                if not isinstance(item, dict):
                    continue
                price_info = item.get("price") or {}
                total = price_info.get("total")
                if total is None:
                    continue
                duration = item.get("duration") or {}
                available = item.get("available") or {}
                offers.append(
                    TripOffer(
                        site=self.name,
                        price=float(total),
                        currency="BRL",
                        price_with_fee=(
                            float(price_info["total_with_platform_fee"])
                            if price_info.get("total_with_platform_fee") is not None
                            else None
                        ),
                        departure=str((item.get("departure") or {}).get("date") or ""),
                        arrival=str((item.get("arrival") or {}).get("date") or ""),
                        duration=format_duration(
                            duration.get("hours"), duration.get("minutes")
                        ),
                        seat_type=str(item.get("transfer_type") or ""),
                        company=str(item.get("provider") or "flixbus"),
                        status=str(item.get("status") or ""),
                        seats_available=(
                            int(available["seats"])
                            if available.get("seats") is not None
                            else None
                        ),
                        uid=str(item.get("uid") or ""),
                        booking_url=booking_url,
                    )
                )
        return sort_offers(offers)
