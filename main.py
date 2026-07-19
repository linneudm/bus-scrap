#!/usr/bin/env python3
"""Ponto de entrada do serviço agendado (cron + comandos + e-mail)."""

from __future__ import annotations

from bus_scrap.scheduler.service import main


if __name__ == "__main__":
    raise SystemExit(main())
