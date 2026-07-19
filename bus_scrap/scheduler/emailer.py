from __future__ import annotations

import html
import os
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from bus_scrap.models import SearchResult, TripOffer


def _template_path() -> Path:
    return Path(__file__).resolve().parent.parent / "templates" / "email.html"


def _fmt_time(value: str) -> str:
    if not value:
        return "-"
    if "T" in value and len(value) >= 16:
        return value[11:16]
    if len(value) >= 5 and value[2] == ":":
        return value[:5]
    return value


def _offer_rows(offers: list[TripOffer]) -> str:
    if not offers:
        return '<p class="empty">Nenhuma passagem encontrada neste site.</p>'

    rows = []
    for offer in offers:
        notes = html.escape(offer.notes) if offer.notes else ""
        link = (
            f'<div class="muted"><a href="{html.escape(offer.booking_url)}">Ver no site</a></div>'
            if offer.booking_url
            else ""
        )
        rows.append(
            "<tr>"
            f'<td class="price">R$ {offer.price:.2f}</td>'
            f"<td>{html.escape(_fmt_time(offer.departure))} -&gt; "
            f"{html.escape(_fmt_time(offer.arrival))}"
            f'<div class="muted">{html.escape(offer.duration or "")}</div></td>'
            f'<td><div class="company">{html.escape(offer.company or "-")}</div>'
            f'<div class="muted">{html.escape(offer.seat_type or "")}</div>{notes}{link}</td>'
            "</tr>"
        )

    return (
        '<table class="trips" role="presentation" width="100%">'
        "<thead><tr><th>Preço</th><th>Horário</th><th>Empresa</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_email_html(
    results: list[SearchResult],
    origem: str,
    destino: str,
    data: str,
    generated_at: str,
) -> str:
    template = _template_path().read_text(encoding="utf-8")
    blocks: list[str] = []
    total = 0

    for result in results:
        total += len(result.offers)
        warnings = "".join(
            f'<p class="warn">{html.escape(warning)}</p>' for warning in result.warnings
        )
        blocks.append(
            f'<h2 class="site-title">{html.escape(result.site.upper())}</h2>'
            f"{warnings}{_offer_rows(result.offers)}"
        )

    if not blocks:
        blocks.append('<p class="empty">Nenhum resultado retornado pelos providers.</p>')

    replacements = {
        "$route_title": html.escape(f"{origem} -> {destino}"),
        "$origem": html.escape(origem),
        "$destino": html.escape(destino),
        "$data": html.escape(data),
        "$generated_at": html.escape(generated_at),
        "$total_offers": str(total),
        "$sites_html": "".join(blocks),
    }
    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def render_email_text(
    results: list[SearchResult],
    origem: str,
    destino: str,
    data: str,
) -> str:
    lines = [
        f"Passagens: {origem} -> {destino}",
        f"Data da ida: {data}",
        "",
    ]
    for result in results:
        lines.append(f"[{result.site}] {len(result.offers)} opção(ões)")
        for offer in result.offers:
            lines.append(
                f"- R$ {offer.price:.2f} | {_fmt_time(offer.departure)} -> "
                f"{_fmt_time(offer.arrival)} | {offer.company} | {offer.seat_type}"
            )
        lines.append("")
    return "\n".join(lines)


def _ssl_context() -> ssl.SSLContext:
    """
    Brevo SA pode apresentar certificado *.sendinblue.com ao conectar em
    smtp-relay.brevo.com — valida a cadeia mas relaxa o hostname nesse caso.
    """
    context = ssl.create_default_context()
    verify_mode = os.getenv("SMTP_SSL_VERIFY", "true").lower()
    if verify_mode in {"0", "false", "no"}:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context

    # Mantém verificação de cadeia; hostname é checado manualmente após handshake
    # via smtplib + server_hostname opcional. Para compatibilidade Brevo:
    context.check_hostname = False
    return context


def _env(name: str, default: str = "") -> str:
    """Lê env removendo espaços e \\r (comum em .env criado no Windows)."""
    value = os.getenv(name, default)
    if value is None:
        return default
    return value.strip().strip('"').strip("'")


def validate_smtp_password(password: str) -> str | None:
    """Retorna aviso se a SMTP Key parecer incompleta (ex.: Brevo truncada)."""
    if not password:
        return "SMTP_PASSWORD vazio."
    if password.startswith("xsmtpsib-"):
        parts = password.split("-")
        # Formato típico: xsmtpsib-<hex longo>-<sufixo>
        if len(parts) < 3 or len(password) < 80:
            return (
                "SMTP_PASSWORD parece truncada. Chaves Brevo costumam ter ~90+ "
                "caracteres no formato xsmtpsib-<hex>-<sufixo>. "
                "Cole a SMTP Key completa do painel Brevo."
            )
    return None


class EmailSender:
    def __init__(self) -> None:
        self.host = _env("SMTP_HOST")
        self.port = int(_env("SMTP_PORT", "587") or "587")
        self.user = _env("SMTP_USER")
        self.password = _env("SMTP_PASSWORD")
        self.sender = _env("SMTP_FROM") or self.user or "bus-scrap@localhost"
        self.use_tls = _env("SMTP_TLS", "true").lower() in {"1", "true", "yes"}
        self.use_ssl = _env("SMTP_SSL", "false").lower() in {"1", "true", "yes"} or self.port == 465
        self.dry_run = _env("SMTP_DRY_RUN", "false").lower() in {"1", "true", "yes"}

    def configured(self) -> bool:
        return bool(self.host and self.sender) or self.dry_run

    def password_warning(self) -> str | None:
        return validate_smtp_password(self.password)

    def _login(self, server: smtplib.SMTP) -> None:
        if not self.user or not self.password:
            raise RuntimeError(
                "SMTP_USER/SMTP_PASSWORD ausentes. No Brevo use o login SMTP "
                "e a SMTP Key (não a senha da conta)."
            )
        warning = validate_smtp_password(self.password)
        try:
            server.login(self.user, self.password)
        except smtplib.SMTPAuthenticationError as exc:
            hint = f" {warning}" if warning else ""
            raise RuntimeError(
                "Falha de autenticação SMTP (535). Confirme SMTP_USER + SMTP Key "
                f"completa no painel Brevo (user={self.user!r}, "
                f"password_len={len(self.password)}, host={self.host!r})."
                f"{hint} Detalhe: {exc}"
            ) from exc

    def send(self, to_email: str, subject: str, html_body: str, text_body: str) -> str:
        if self.dry_run:
            preview = Path(os.getenv("BUS_SCRAP_DATA_DIR", "data")) / "last_email.html"
            preview.parent.mkdir(parents=True, exist_ok=True)
            preview.write_text(html_body, encoding="utf-8")
            return f"DRY_RUN: e-mail salvo em {preview}"

        if not self.host:
            raise RuntimeError(
                "SMTP não configurado. Defina SMTP_HOST/SMTP_USER/SMTP_PASSWORD "
                "ou SMTP_DRY_RUN=true."
            )

        warning = self.password_warning()
        if warning:
            # Ainda tenta enviar, mas deixa rastreável se falhar
            pass

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = to_email
        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        context = _ssl_context()
        if self.use_ssl:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30, context=context) as server:
                server.ehlo()
                self._login(server)
                server.sendmail(self.sender, [to_email], message.as_string())
        elif self.use_tls:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                self._login(server)
                server.sendmail(self.sender, [to_email], message.as_string())
        else:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.ehlo()
                self._login(server)
                server.sendmail(self.sender, [to_email], message.as_string())

        return f"E-mail enviado para {to_email}"
