from __future__ import annotations

from bus_scrap.scheduler.config import ConfigStore, default_stop_path
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

Via Docker (sem attach):
  docker exec bus-scrap bus-ctl show
  docker exec bus-scrap bus-ctl set destino Natal
  docker exec bus-scrap bus-ctl run
""".strip()


class CommandHandler:
    def __init__(
        self,
        store: ConfigStore,
        job: DailySearchJob,
        logger: RuntimeLogger,
        *,
        external: bool = False,
    ) -> None:
        self.store = store
        self.job = job
        self.logger = logger
        self.external = external
        self.should_stop = False

    def handle(self, line: str) -> int:
        text = (line or "").strip()
        if not text:
            return 0

        parts = text.split()
        cmd = parts[0].lower()

        if cmd in {"help", "?"}:
            self.logger.help_text(HELP_TEXT)
            return 0

        if cmd in {"show", "status"}:
            cfg = self.store.get()
            self.logger.info(
                "Config atual | "
                f"email={cfg.email} | origem={cfg.origem} | destino={cfg.destino} | "
                f"data={cfg.data} | site={cfg.site} | limit={cfg.limit} | "
                f"cron={cfg.cron_hour:02d}:{cfg.cron_minute:02d} ({cfg.timezone})"
            )
            return 0

        if cmd == "set":
            if len(parts) < 3:
                self.logger.error("Uso: set <campo> <valor>")
                return 1
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
                return 1
            return 0

        if cmd == "run":
            self.logger.info("Execução manual solicitada.")
            ok = self.job.run(trigger="manual" if not self.external else "exec")
            return 0 if ok else 1

        if cmd in {"quit", "exit"}:
            stop_path = default_stop_path()
            stop_path.parent.mkdir(parents=True, exist_ok=True)
            stop_path.write_text("stop\n", encoding="utf-8")
            self.should_stop = True
            if self.external:
                self.logger.info(
                    f"Pedido de encerramento gravado em {stop_path}. "
                    "O serviço principal deve parar em instantes."
                )
            else:
                self.logger.info("Encerrando serviço...")
            return 0

        self.logger.error(f"Comando desconhecido: {cmd}. Digite 'help'.")
        return 1
