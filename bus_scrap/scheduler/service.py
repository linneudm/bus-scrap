from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from bus_scrap.scheduler.commands import CommandHandler, HELP_TEXT
from bus_scrap.scheduler.config import ConfigStore, default_stop_path
from bus_scrap.scheduler.emailer import EmailSender
from bus_scrap.scheduler.job import DailySearchJob
from bus_scrap.scheduler.logger import RuntimeLogger


class SchedulerService:
    def __init__(self, store: ConfigStore, logger: RuntimeLogger) -> None:
        self.store = store
        self.logger = logger
        self.job = DailySearchJob(store, logger, EmailSender())
        self.commands = CommandHandler(store, self.job, logger)
        self._last_run_key: str | None = None
        self._stop = threading.Event()

    def _consume_stop_request(self) -> bool:
        stop_path = default_stop_path()
        if not stop_path.exists():
            return False
        try:
            stop_path.unlink(missing_ok=True)
        except OSError:
            pass
        self.logger.info("Pedido de encerramento recebido (bus-ctl quit).")
        self.commands.should_stop = True
        self._stop.set()
        return True

    def _tz(self):
        cfg = self.store.get()
        try:
            return ZoneInfo(cfg.timezone)
        except Exception:
            try:
                return ZoneInfo("America/Sao_Paulo")
            except Exception:
                # Windows sem tzdata: UTC-3 fixo (horário de Brasília padrão)
                from datetime import timezone, timedelta

                self.logger.warn(
                    "tzdata indisponível; usando UTC-3 fixo para o cron."
                )
                return timezone(timedelta(hours=-3))

    def _maybe_run_cron(self) -> None:
        cfg = self.store.get()
        now = datetime.now(self._tz())
        if now.hour != cfg.cron_hour or now.minute != cfg.cron_minute:
            return
        run_key = now.strftime("%Y-%m-%d %H:%M")
        if self._last_run_key == run_key:
            return
        self._last_run_key = run_key
        self.logger.info(
            f"Cron disparado às {cfg.cron_hour:02d}:{cfg.cron_minute:02d} "
            f"({cfg.timezone})"
        )
        self.job.run(trigger="cron")

    def _stdin_loop(self) -> None:
        self.logger.info("Escutando comandos no terminal. Digite 'help' para ver opções.")
        while not self._stop.is_set() and not self.commands.should_stop:
            try:
                line = sys.stdin.readline()
            except Exception as exc:  # noqa: BLE001
                self.logger.error(f"Falha ao ler comando: {exc}")
                break
            if line == "":
                # EOF (ex.: container sem TTY) — mantém só o cron
                self.logger.warn(
                    "STDIN fechado. Continuando apenas com o agendamento diário."
                )
                break
            self.commands.handle(line)
            if self.commands.should_stop:
                self._stop.set()
                break

    def run_forever(self, run_now: bool = False) -> int:
        # Limpa pedido de stop residual de execução anterior
        stop_path = default_stop_path()
        if stop_path.exists():
            stop_path.unlink(missing_ok=True)

        cfg = self.store.get()
        self.logger.section("Bus Scrap Scheduler iniciado")
        self.logger.info(
            f"Agendamento diário: {cfg.cron_hour:02d}:{cfg.cron_minute:02d} "
            f"({cfg.timezone})"
        )
        self.logger.info(
            f"Rota padrão: {cfg.origem} -> {cfg.destino} | ida {cfg.data} | "
            f"email {cfg.email}"
        )
        self.logger.info("Comandos também via: docker exec bus-scrap bus-ctl <cmd>")
        self.logger.help_text(HELP_TEXT)

        if run_now:
            self.job.run(trigger="startup")

        stdin_thread = threading.Thread(target=self._stdin_loop, name="commands", daemon=True)
        stdin_thread.start()

        try:
            while not self._stop.is_set() and not self.commands.should_stop:
                if self._consume_stop_request():
                    break
                self._maybe_run_cron()
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Interrompido pelo usuário (Ctrl+C).")
        finally:
            self._stop.set()
            self.logger.info("Serviço finalizado.")
        return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Serviço diário de busca de passagens com envio por e-mail "
            "e comandos interativos."
        )
    )
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Executa uma busca/envio imediatamente ao iniciar",
    )
    parser.add_argument(
        "--email",
        help="Define o e-mail destinatário inicial",
    )
    parser.add_argument("--origem", help="Define a origem inicial")
    parser.add_argument("--destino", help="Define o destino inicial")
    parser.add_argument("--data", help="Define a data da ida inicial (DD/MM/YYYY)")
    parser.add_argument("--site", help="Provider inicial (all/flixbus/clickbus/queropassagem)")
    parser.add_argument("--limit", type=int, help="Limite de passagens por site")
    parser.add_argument("--cron-hour", type=int, dest="cron_hour", help="Hora do cron (0-23)")
    parser.add_argument(
        "--cron-minute", type=int, dest="cron_minute", help="Minuto do cron (0-59)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    from bus_scrap.scheduler.env_loader import load_dotenv_files

    load_dotenv_files()

    parser = build_parser()
    args = parser.parse_args(argv)
    logger = RuntimeLogger()
    store = ConfigStore()

    updates = {}
    if args.email:
        updates["email"] = args.email
    if args.origem:
        updates["origem"] = args.origem
    if args.destino:
        updates["destino"] = args.destino
    if args.data:
        updates["data"] = args.data
    if args.site:
        updates["site"] = args.site
    if args.limit is not None:
        updates["limit"] = args.limit
    if args.cron_hour is not None:
        updates["cron_hour"] = args.cron_hour
    if args.cron_minute is not None:
        updates["cron_minute"] = args.cron_minute
    if updates:
        store.update(**updates)
        logger.success("Configuração inicial aplicada via argumentos.")

    # Garante dry-run útil em ambiente local sem SMTP
    if not os.getenv("SMTP_HOST") and not os.getenv("SMTP_DRY_RUN"):
        os.environ.setdefault("SMTP_DRY_RUN", "true")
        logger.warn("SMTP_HOST ausente — ativando SMTP_DRY_RUN=true por padrão.")

    service = SchedulerService(store, logger)
    return service.run_forever(run_now=args.run_now)


if __name__ == "__main__":
    raise SystemExit(main())
