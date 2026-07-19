from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from bus_scrap.http_util import http_get, http_get_json
from bus_scrap.models import Location, SearchResult, TripOffer
from bus_scrap.providers.base import Provider, rank_location_name, sort_offers

PLACES_URL = "https://bff.clickbus.com/web/api/v4/places"
SITE = "https://www.clickbus.com.br"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


class ClickBusProvider(Provider):
    """ClickBus: places via BFF + trips via sessão de navegador (Playwright).

    A API `/trips` exige proteção anti-bot (ST). Cookies falsos / TLS spoof
    não bastam. Com Playwright instalado, abrimos a página de busca e
    interceptamos a resposta autenticada do BFF.
    """

    name = "clickbus"
    aliases = ("clickbus.com.br", "click")

    def search(
        self,
        origin_query: str,
        destination_query: str,
        travel_date: datetime,
    ) -> SearchResult:
        origin = self._resolve_place(origin_query)
        destination = self._resolve_place(destination_query)
        offers, warnings = self._search_trips(origin, destination, travel_date)
        return SearchResult(
            site=self.name,
            origin=origin,
            destination=destination,
            travel_date=travel_date,
            offers=sort_offers(offers),
            warnings=warnings,
        )

    def _resolve_place(self, query: str) -> Location:
        params = urlencode(
            {
                "clientId": 1,
                "limit": 12,
                "name": query,
                "fields": "id,name,slug",
            }
        )
        results = http_get_json(
            f"{PLACES_URL}?{params}",
            headers={
                "Origin": SITE,
                "Referer": f"{SITE}/",
                "Accept": "application/json",
            },
        )
        if not isinstance(results, list) or not results:
            raise ValueError(f"ClickBus: nenhum local encontrado para '{query}'.")

        best = max(
            results, key=lambda item: rank_location_name(query, str(item.get("name", "")))
        )
        return Location(
            id=str(best.get("id") or ""),
            name=str(best.get("name") or query),
            slug=str(best.get("slug") or ""),
        )

    def _search_trips(
        self,
        origin: Location,
        destination: Location,
        travel_date: datetime,
    ) -> tuple[list[TripOffer], list[str]]:
        date_iso = travel_date.strftime("%Y-%m-%d")
        date_br = travel_date.strftime("%d/%m/%Y")
        booking_url = (
            f"{SITE}/onibus/{origin.slug}/{destination.slug}"
            f"?departureDate={date_iso}"
        )
        warnings: list[str] = []
        offers: list[TripOffer] = []

        # 1) Sessão real via Playwright (horários individuais)
        browser_offers, browser_warning = self._fetch_trips_with_browser(
            booking_url, origin.slug, destination.slug, date_iso
        )
        if browser_warning:
            warnings.append(browser_warning)
        offers.extend(browser_offers)

        # 2) Fallback: AggregateOffer da página SSR
        if not offers:
            html = http_get(booking_url, headers={"Accept": "text/html"})
            next_data = self._extract_next_data(html)
            if next_data:
                page_data = (
                    next_data.get("props", {})
                    .get("pageProps", {})
                    .get("pageData", {})
                )
                for item in (page_data.get("trips") or {}).get("departures") or []:
                    offer = self._parse_departure(item, booking_url)
                    if offer:
                        offers.append(offer)

            if not offers:
                aggregate = self._extract_aggregate_offer(html)
                if aggregate:
                    low = float(aggregate["lowPrice"])
                    high = float(aggregate.get("highPrice") or low)
                    count = int(float(aggregate.get("offerCount") or 1))
                    warnings.append(
                        "ClickBus retornou apenas faixa de preços (AggregateOffer). "
                        "Instale Playwright para horários individuais: "
                        "pip install playwright && python -m playwright install chromium"
                    )
                    offers.append(
                        TripOffer(
                            site=self.name,
                            price=low,
                            company="clickbus",
                            status="from_price",
                            booking_url=booking_url,
                            notes=(
                                f"A partir de R$ {low:.2f} "
                                f"(até R$ {high:.2f}, {count} opções em {date_br})"
                            ),
                        )
                    )
                else:
                    warnings.append("ClickBus: nenhuma passagem encontrada.")

        return offers, warnings

    def _fetch_trips_with_browser(
        self,
        booking_url: str,
        origin_slug: str,
        destination_slug: str,
        date_iso: str,
    ) -> tuple[list[TripOffer], str | None]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return [], (
                "Playwright não instalado; usando fallback AggregateOffer. "
                "Para horários: pip install playwright && "
                "python -m playwright install chromium"
            )

        captured: list[dict[str, Any]] = []

        def on_response(response: Any) -> None:
            url = response.url
            if "/trips?" not in url or "lowest-price" in url:
                return
            if response.request.method != "GET":
                return
            # garante que é a busca da rota pedida
            if origin_slug not in url or destination_slug not in url:
                return
            if date_iso not in url:
                return
            try:
                if response.status != 200:
                    return
                data = response.json()
            except Exception:
                return
            if isinstance(data, dict):
                captured.append(data)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="pt-BR",
                )
                page = context.new_page()
                page.on("response", on_response)
                page.goto(booking_url, wait_until="domcontentloaded", timeout=60000)
                # Aguarda a chamada autenticada do BFF
                for _ in range(30):
                    if captured:
                        break
                    page.wait_for_timeout(500)
                browser.close()
        except Exception as exc:  # noqa: BLE001
            return [], f"Falha na sessão Playwright do ClickBus: {exc}"

        if not captured:
            return [], (
                "Sessão Playwright não capturou /trips (timeout ou bloqueio). "
                "Usando fallback AggregateOffer."
            )

        offers: list[TripOffer] = []
        for payload in captured:
            departures = payload.get("departures")
            if departures is None and isinstance(payload.get("trips"), dict):
                departures = payload["trips"].get("departures")
            for item in departures or []:
                offer = self._parse_departure(item, booking_url)
                if offer:
                    offers.append(offer)
        return offers, None

    def _extract_next_data(self, html: str) -> dict[str, Any] | None:
        match = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S
        )
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None

    def _extract_aggregate_offer(self, html: str) -> dict[str, Any] | None:
        for match in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.S | re.I,
        ):
            try:
                data = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                offers = item.get("offers")
                if isinstance(offers, dict) and offers.get("@type") == "AggregateOffer":
                    if offers.get("lowPrice") is not None:
                        return offers
        return None

    def _parse_departure(self, item: dict[str, Any], booking_url: str) -> TripOffer | None:
        price = item.get("discountedPrice")
        if price is None:
            price = item.get("price")
        if isinstance(price, dict):
            price = (
                price.get("value")
                or price.get("total")
                or price.get("amount")
                or price.get("bestPrice")
            )
        if price is None:
            price = item.get("priceValue") or item.get("lowestPrice")
        if price is None:
            return None

        departure = item.get("departure") or {}
        arrival = item.get("arrival") or {}
        dep_schedule = departure.get("schedule") or {}
        arr_schedule = arrival.get("schedule") or {}

        dep_date = str(dep_schedule.get("date") or "")
        dep_time = str(dep_schedule.get("time") or "")
        arr_date = str(arr_schedule.get("date") or "")
        arr_time = str(arr_schedule.get("time") or "")

        if dep_date and dep_time:
            departure_iso = f"{dep_date}T{dep_time}"
        else:
            departure_iso = str(
                departure.get("date") or item.get("departureTime") or dep_time
            )

        if arr_date and arr_time:
            arrival_iso = f"{arr_date}T{arr_time}"
        else:
            arrival_iso = str(arrival.get("date") or item.get("arrivalTime") or arr_time)

        company = item.get("travelCompany") or item.get("company") or {}
        company_name = (
            company.get("name")
            if isinstance(company, dict)
            else str(company or "clickbus")
        )
        service = item.get("serviceClass") or item.get("anttServiceClass") or {}
        seat = service.get("name") if isinstance(service, dict) else str(service or "")

        duration_obj = item.get("duration") or {}
        if isinstance(duration_obj, dict):
            duration = str(duration_obj.get("hours") or duration_obj.get("days") or "")
        else:
            duration = str(duration_obj or "")

        seats = item.get("availableSeats")
        uuids = item.get("tripUuids") or []
        uid = (
            uuids[0]
            if isinstance(uuids, list) and uuids
            else str(item.get("uuid") or item.get("id") or "")
        )

        return TripOffer(
            site=self.name,
            price=float(price),
            currency=str(item.get("currency") or "BRL"),
            departure=departure_iso,
            arrival=arrival_iso,
            duration=duration,
            seat_type=seat,
            company=str(company_name or "clickbus"),
            status="available" if item.get("isReservable", True) else "unavailable",
            seats_available=int(seats) if seats is not None else None,
            uid=str(uid),
            booking_url=booking_url,
        )
