"""Carrega .env do projeto (se existir) antes de ler SMTP_* e demais configs."""

from __future__ import annotations

from pathlib import Path


def load_dotenv_files() -> list[str]:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return []

    loaded: list[str] = []
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[2] / ".env",
    ]
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        # override=False: env já definida no container/Docker tem prioridade
        if load_dotenv(resolved, override=False):
            loaded.append(str(resolved))
    return loaded
