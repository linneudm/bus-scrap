from __future__ import annotations

from bus_scrap.scheduler.config import ConfigStore
from bus_scrap.scheduler.job import DailySearchJob
from bus_scrap.scheduler.logger import RuntimeLogger

HELP_TEXT = """
Comandos disponíveis:
  help                         Mostra esta ajuda
  show | status                Mostra a configuração atual
  set email <endereco>         Altera o e-mail destinatário
  set origem <cidade>          Altera a origem
  set destino <cidade>         Altera o destino
  set data <DD/MM/YYYY>        Altera a data da ida
  set site <flixbus|clickbus|queropassagem|all>
  set limit <n>                Limite de passagens por site
  set cron_hour <0-23>         Hora do envio diário
  set cron_minute <0-59>       Minuto do envio diário
  run                          Executa busca + e-mail agora
  quit | exit                  Encerra o serviço
""".strip()


class CommandHandler:
    def __init__(
        self,
        store: ConfigStore,
        job: DailySearchJob,
        logger: RuntimeLogger,
    ) -> None:
        self.store = store
        self.job = job
        self.logger = logger
        self.should_stop = False

    def handle(self, line: str) -> None:
        text = (line or "").strip()
        if not text:
            return

        parts = text.split()
        cmd = parts[0].lower()

        if cmd in {"help", "?"}:
            self.logger.help_text(HELP_TEXT)
            return

        if cmd in {"show", "status"}:
            cfg = self.store.get()
            self.logger.info(
                "Config atual | "
                f"email={cfg.email} | origem={cfg.origem} | destino={cfg.destino} | "
                f"data={cfg.data} | site={cfg.site} | limit={cfg.limit} | "
                f"cron={cfg.cron_hour:02d}:{cfg.cron_minute:02d} ({cfg.timezone})"
            )
            return

        if cmd == "set":
            if len(parts) < 3:
                self.logger.error("Uso: set <campo> <valor>")
                return
            field = parts[1].lower()
            value = " ".join(parts[2:]).strip()
            alias = {
                "e-mail": "email",
                "mail": "email",
                "from": "origem",
                "to": "destino",
                "date": "data",
            }
            field = alias.get(field, field)
            try:
                cfg = self.store.update(**{field: value})
                self.logger.success(
                    f"Parâmetro '{field}' atualizado para '{getattr(cfg, field)}'"
                )
            except Exception as exc:  # noqa: BLE001
                self.logger.error(f"Não foi possível atualizar '{field}': {exc}")
            return

        if cmd == "run":
            self.logger.info("Execução manual solicitada.")
            self.job.run(trigger="manual")
            return

        if cmd in {"quit", "exit"}:
            self.should_stop = True
            self.logger.info("Encerrando serviço...")
            return

        self.logger.error(f"Comando desconhecido: {cmd}. Digite 'help'.")
