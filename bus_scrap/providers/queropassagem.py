from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from bus_scrap.http_util import http_get
from bus_scrap.models import Location, SearchResult, TripOffer
from bus_scrap.providers.base import Provider, normalize, rank_location_name, sort_offers

SITE = "https://queropassagem.com.br"
CITIES_META_URL = f"{SITE}/mgds_cidades_busca.php?origemBusca=1"
CITIES_JS_URL = f"{SITE}/js/cidades-busca/mgds_cidades_busca_org1.js"


class QueroPassagemProvider(Provider):
    name = "queropassagem"
    aliases = ("queropassagem.com.br", "quero", "qp")

    _cities_cache: list[dict[str, Any]] | None = None

    def search(
        self,
        origin_query: str,
        destination_query: str,
        travel_date: datetime,
    ) -> SearchResult:
        origin = self._resolve_city(origin_query)
        destination = self._resolve_city(destination_query)
        offers, warnings = self._search_trips(origin, destination, travel_date)
        return SearchResult(
            site=self.name,
            origin=origin,
            destination=destination,
            travel_date=travel_date,
            offers=sort_offers(offers),
            warnings=warnings,
        )

    def _load_cities(self) -> list[dict[str, Any]]:
        if self._cities_cache is not None:
            return self._cities_cache
        bust = http_get(CITIES_META_URL).strip()
        raw = http_get(f"{CITIES_JS_URL}?{bust}")
        data = json.loads(raw)
        if not isinstance(data, list):
            raise RuntimeError("QueroPassagem: índice de cidades inválido.")
        QueroPassagemProvider._cities_cache = data
        return data

    def _flatten_cities(self) -> list[dict[str, Any]]:
        flat: list[dict[str, Any]] = []
        for item in self._load_cities():
            flat.append(item)
            for child in item.get("filhos") or []:
                flat.append(child)
        return flat

    def _resolve_city(self, query: str) -> Location:
        candidates = self._flatten_cities()
        needle = normalize(query)

        def rank(item: dict[str, Any]) -> tuple:
            display = str(item.get("nome_display") or "")
            search_name = str(item.get("nome_pesquisa") or "")
            tipo = str(item.get("tipo") or "")
            base = rank_location_name(query, display)
            search_hit = needle in normalize(search_name)
            city_boost = tipo == "cidade"
            return (*base, search_hit, city_boost)

        best = max(candidates, key=rank)
        display = str(best.get("nome_display") or query)
        if needle not in normalize(display) and needle not in normalize(
            str(best.get("nome_pesquisa") or "")
        ):
            raise ValueError(f"QueroPassagem: nenhum local encontrado para '{query}'.")

        return Location(
            id=str(best.get("id") or ""),
            name=display,
            slug=str(best.get("url") or ""),
            meta={"tipo": str(best.get("tipo") or "")},
        )

    def _search_trips(
        self,
        origin: Location,
        destination: Location,
        travel_date: datetime,
    ) -> tuple[list[TripOffer], list[str]]:
        date_br = travel_date.strftime("%d/%m/%Y")
        path = f"/onibus/{origin.slug}-para-{destination.slug}"
        booking_url = f"{SITE}{path}?data={date_br}"
        warnings: list[str] = []

        try:
            html = http_get(booking_url, headers={"Accept": "text/html"})
        except RuntimeError:
            # fallback: tenta slug de terminal filho mais comum
            alt_origin = origin.slug.replace("-todas-", "-").replace("-todos-", "-")
            alt_dest = destination.slug.replace("-todas-", "-").replace("-todos-", "-")
            booking_url = f"{SITE}/onibus/{alt_origin}-para-{alt_dest}?data={date_br}"
            html = http_get(booking_url, headers={"Accept": "text/html"})
            warnings.append("URL ajustada para slugs alternativos.")

        offers = self._parse_schema_offers(html, booking_url)
        if not offers:
            # tenta sem query de data (página canônica da rota)
            canonical = booking_url.split("?")[0]
            html = http_get(canonical, headers={"Accept": "text/html"})
            offers = self._parse_schema_offers(html, booking_url)
            if offers:
                warnings.append(
                    "Passagens extraídas da página da rota "
                    "(datas podem variar; confira no site)."
                )

        if not offers:
            warnings.append("QueroPassagem: nenhuma passagem encontrada.")

        return offers, warnings

    def _parse_schema_offers(self, html: str, booking_url: str) -> list[TripOffer]:
        offers: list[TripOffer] = []
        blobs: list[Any] = []

        for match in re.finditer(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            html,
            re.S | re.I,
        ):
            try:
                blobs.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                continue

        # Product AggregateOffer embutido (pode não ter type="ld+json")
        for pattern in (
            r'(\[\{"name":"Passagens de.*?\}\])\s*</script>',
            r'(\{"@context":"https://schema.org","@type":"Product".*?\})\s*</script>',
        ):
            match = re.search(pattern, html, re.S)
            if not match:
                continue
            try:
                blobs.append(json.loads(match.group(1)))
            except json.JSONDecodeError:
                continue

        if not blobs:
            match = re.search(r'(\[\{[^\]]*"AggregateOffer".*?\}\])', html, re.S)
            if match:
                try:
                    blobs.append(json.loads(match.group(1)))
                except json.JSONDecodeError:
                    pass

        for blob in blobs:
            items = blob if isinstance(blob, list) else [blob]
            for item in items:
                if not isinstance(item, dict):
                    continue
                offer_block = item.get("offers")
                if not isinstance(offer_block, dict):
                    continue

                detailed = offer_block.get("offers")
                if isinstance(detailed, list) and detailed:
                    for entry in detailed:
                        if not isinstance(entry, dict):
                            continue
                        price = entry.get("price")
                        if price is None:
                            continue
                        offers.append(
                            TripOffer(
                                site=self.name,
                                price=float(price),
                                currency=str(entry.get("priceCurrency") or "BRL"),
                                company=str(entry.get("seller") or ""),
                                status="available",
                                booking_url=booking_url,
                                uid=str(entry.get("sku") or entry.get("@id") or ""),
                            )
                        )
                elif offer_block.get("@type") == "AggregateOffer":
                    low = offer_block.get("lowPrice")
                    if low is None:
                        continue
                    high = offer_block.get("highPrice")
                    count = offer_block.get("offerCount")
                    notes = f"A partir de R$ {float(low):.2f}"
                    if high is not None:
                        notes += f" (até R$ {float(high):.2f}"
                        if count is not None:
                            notes += f", {count} opções"
                        notes += ")"
                    offers.append(
                        TripOffer(
                            site=self.name,
                            price=float(low),
                            currency=str(offer_block.get("priceCurrency") or "BRL"),
                            company="queropassagem",
                            status="from_price",
                            booking_url=booking_url,
                            notes=notes,
                        )
                    )

        unique: dict[tuple, TripOffer] = {}
        for offer in offers:
            key = (offer.price, offer.company, offer.notes)
            unique[key] = offer
        return list(unique.values())
