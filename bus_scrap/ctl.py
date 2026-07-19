#!/usr/bin/env python3
"""CLI para comandos via docker exec (sem attach).

Exemplos:
  python -m bus_scrap.ctl show
  python -m bus_scrap.ctl set destino Natal
  python -m bus_scrap.ctl run
  docker exec bus-scrap bus-ctl status
"""

from __future__ import annotations

import sys

from bus_scrap.scheduler.commands import HELP_TEXT, CommandHandler
from bus_scrap.scheduler.config import ConfigStore
from bus_scrap.scheduler.emailer import EmailSender
from bus_scrap.scheduler.env_loader import load_dotenv_files
from bus_scrap.scheduler.job import DailySearchJob
from bus_scrap.scheduler.logger import RuntimeLogger


def main(argv: list[str] | None = None) -> int:
    load_dotenv_files()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(HELP_TEXT, flush=True)
        return 0

    logger = RuntimeLogger()
    store = ConfigStore()
    job = DailySearchJob(store, logger, EmailSender())
    handler = CommandHandler(store, job, logger, external=True)
    return handler.handle(" ".join(args))


if __name__ == "__main__":
    raise SystemExit(main())
