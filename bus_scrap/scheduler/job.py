from __future__ import annotations

from datetime import datetime

from bus_scrap.providers import resolve_providers
from bus_scrap.scheduler.config import ConfigStore
from bus_scrap.scheduler.emailer import EmailSender, render_email_html, render_email_text
from bus_scrap.scheduler.logger import RuntimeLogger


class DailySearchJob:
    def __init__(
        self,
        store: ConfigStore,
        logger: RuntimeLogger,
        emailer: EmailSender | None = None,
    ) -> None:
        self.store = store
        self.logger = logger
        self.emailer = emailer or EmailSender()

    def run(self, trigger: str = "cron") -> bool:
        config = self.store.get()
        self.logger.section(
            f"Início do ciclo ({trigger}) | {config.origem} -> {config.destino} | "
            f"ida {config.data} | para {config.email}"
        )

        try:
            travel_date = config.travel_date()
        except ValueError as exc:
            self.logger.error(f"Data inválida na configuração: {exc}")
            return False

        if not self.emailer.configured():
            self.logger.error(
                "SMTP não configurado. Defina variáveis SMTP_* ou SMTP_DRY_RUN=true."
            )
            return False

        password_warning = self.emailer.password_warning()
        if password_warning:
            self.logger.warn(password_warning)

        results = []
        errors: list[str] = []
        try:
            providers = resolve_providers(config.site)
        except ValueError as exc:
            self.logger.error(str(exc))
            return False

        for provider in providers:
            self.logger.info(f"Consultando provider [{provider.name}]...")
            try:
                result = provider.search(config.origem, config.destino, travel_date)
                if config.limit and config.limit > 0:
                    result.offers = result.offers[: config.limit]
                results.append(result)
                self.logger.success(
                    f"[{provider.name}] {len(result.offers)} passagem(ns) encontrada(s)"
                )
                for warning in result.warnings:
                    self.logger.warn(f"[{provider.name}] {warning}")
            except Exception as exc:  # noqa: BLE001
                msg = f"[{provider.name}] falha: {exc}"
                errors.append(msg)
                self.logger.error(msg)

        generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
        subject = (
            f"Passagens {config.origem} → {config.destino} | "
            f"ida {config.data} | {generated_at}"
        )
        html_body = render_email_html(
            results,
            origem=config.origem,
            destino=config.destino,
            data=config.data,
            generated_at=generated_at,
        )
        text_body = render_email_text(
            results,
            origem=config.origem,
            destino=config.destino,
            data=config.data,
        )

        try:
            status = self.emailer.send(
                to_email=config.email,
                subject=subject,
                html_body=html_body,
                text_body=text_body,
            )
            self.logger.success(status)
            if errors:
                self.logger.warn(
                    "Ciclo concluído com erros parciais: " + " | ".join(errors)
                )
            else:
                self.logger.success("Ciclo concluído com sucesso.")
            return True
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"Falha no envio de e-mail: {exc}")
            return False
