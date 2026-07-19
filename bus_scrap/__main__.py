#!/usr/bin/env python3
"""CLI unificado para busca de passagens em múltiplos sites."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from bus_scrap.models import SearchResult
from bus_scrap.providers import list_sites, resolve_providers


def parse_date_br(value: str) -> datetime:
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data inválida '{value}'. Use o formato DD/MM/YYYY."
        ) from exc


def configure_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def print_human(result: SearchResult) -> None:
    print(
        f"[{result.site}] {result.origin.name} -> {result.destination.name} | "
        f"ida {result.travel_date.strftime('%d/%m/%Y')}"
    )
    for warning in result.warnings:
        print(f"Aviso: {warning}")

    if not result.offers:
        print("Nenhuma passagem encontrada.\n")
        return

    print(f"{len(result.offers)} opção(ões):\n")
    for index, offer in enumerate(result.offers, start=1):
        fee = (
            f" (com taxa: R$ {offer.price_with_fee:.2f})"
            if offer.price_with_fee is not None
            else ""
        )
        company = f" | {offer.company}" if offer.company else ""
        seat = f" | {offer.seat_type}" if offer.seat_type else ""
        duration = f" | {offer.duration}" if offer.duration else ""
        dep = offer.departure[11:16] if len(offer.departure) >= 16 else offer.departure
        arr = offer.arrival[11:16] if len(offer.arrival) >= 16 else offer.arrival
        time_part = ""
        if dep or arr:
            time_part = f" | {dep or '?'} -> {arr or '?'}"
        notes = f" | {offer.notes}" if offer.notes else ""
        print(
            f"{index}. R$ {offer.price:.2f}{fee}{time_part}{duration}{seat}{company}{notes}"
        )
    print()


def build_parser() -> argparse.ArgumentParser:
    sites = ", ".join(list_sites())
    parser = argparse.ArgumentParser(
        description=(
            "Busca preços de passagens de ônibus em FlixBus, ClickBus e QueroPassagem."
        )
    )
    parser.add_argument("--origem", required=True, help="Cidade de origem")
    parser.add_argument("--destino", required=True, help="Cidade de destino")
    parser.add_argument(
        "--data",
        required=True,
        type=parse_date_br,
        help="Data da ida no formato DD/MM/YYYY",
    )
    parser.add_argument(
        "--site",
        default="all",
        help=f"Site alvo: {sites}, all (padrão: all)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime o resultado em JSON",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limita a quantidade de passagens exibidas por site (0 = todas)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        providers = resolve_providers(args.site)
    except ValueError as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1

    results: list[SearchResult] = []
    errors: list[dict[str, str]] = []

    for provider in providers:
        try:
            result = provider.search(args.origem, args.destino, args.data)
            if args.limit and args.limit > 0:
                result.offers = result.offers[: args.limit]
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - reportar falha por site
            errors.append({"site": provider.name, "erro": str(exc)})
            if not args.json:
                print(f"[{provider.name}] Erro: {exc}\n", file=sys.stderr)

    if args.json:
        payload = {
            "origem": args.origem,
            "destino": args.destino,
            "data": args.data.strftime("%d/%m/%Y"),
            "sites": [result.to_dict() for result in results],
            "erros": errors,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if not results and errors:
            return 1
        for result in results:
            print_human(result)

    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
