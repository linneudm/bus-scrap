from __future__ import annotations

from bus_scrap.providers.base import Provider
from bus_scrap.providers.clickbus import ClickBusProvider
from bus_scrap.providers.flixbus import FlixBusProvider
from bus_scrap.providers.queropassagem import QueroPassagemProvider

PROVIDERS: dict[str, Provider] = {
    FlixBusProvider.name: FlixBusProvider(),
    ClickBusProvider.name: ClickBusProvider(),
    QueroPassagemProvider.name: QueroPassagemProvider(),
}

_ALIAS_MAP: dict[str, str] = {}
for provider in PROVIDERS.values():
    _ALIAS_MAP[provider.name] = provider.name
    for alias in provider.aliases:
        _ALIAS_MAP[alias.lower()] = provider.name


def list_sites() -> list[str]:
    return sorted(PROVIDERS.keys())


def resolve_provider(site: str) -> Provider:
    key = _ALIAS_MAP.get(site.strip().lower())
    if not key:
        known = ", ".join(list_sites())
        raise ValueError(f"Site desconhecido '{site}'. Use: {known}, all")
    return PROVIDERS[key]


def resolve_providers(site: str) -> list[Provider]:
    if site.strip().lower() in {"all", "*", "todos"}:
        return [PROVIDERS[name] for name in list_sites()]
    return [resolve_provider(site)]
