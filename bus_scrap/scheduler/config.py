from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_CONFIG = {
    "email": "seu-email@exemplo.com",
    "origem": "Fortaleza",
    "destino": "Recife",
    "data": "15/09/2026",
    "site": "all",
    "limit": 15,
    "cron_hour": 10,
    "cron_minute": 0,
    "timezone": "America/Sao_Paulo",
}


def default_config_path() -> Path:
    override = os.getenv("BUS_SCRAP_CONFIG")
    if override:
        return Path(override)
    return Path(os.getenv("BUS_SCRAP_DATA_DIR", "data")) / "config.json"


@dataclass
class AppConfig:
    email: str
    origem: str
    destino: str
    data: str
    site: str = "all"
    limit: int = 15
    cron_hour: int = 10
    cron_minute: int = 0
    timezone: str = "America/Sao_Paulo"

    def travel_date(self) -> datetime:
        return datetime.strptime(self.data.strip(), "%d/%m/%Y")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        merged = {**DEFAULT_CONFIG, **(raw or {})}
        return cls(
            email=str(merged["email"]),
            origem=str(merged["origem"]),
            destino=str(merged["destino"]),
            data=str(merged["data"]),
            site=str(merged.get("site") or "all"),
            limit=int(merged.get("limit") or 15),
            cron_hour=int(merged.get("cron_hour", 10)),
            cron_minute=int(merged.get("cron_minute", 0)),
            timezone=str(merged.get("timezone") or "America/Sao_Paulo"),
        )


class ConfigStore:
    """Config persistente e thread-safe, editável em runtime."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_config_path()
        self._lock = threading.RLock()
        self._config = AppConfig.from_dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> AppConfig:
        with self._lock:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                self._config = AppConfig.from_dict(raw)
            else:
                self.save()
            return deepcopy(self._config)

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._config.to_dict(), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    def get(self) -> AppConfig:
        with self._lock:
            return deepcopy(self._config)

    def update(self, **kwargs: object) -> AppConfig:
        with self._lock:
            current = self._config.to_dict()
            for key, value in kwargs.items():
                if key not in current:
                    raise KeyError(f"Parâmetro desconhecido: {key}")
                if value is None:
                    continue
                if key == "data":
                    datetime.strptime(str(value).strip(), "%d/%m/%Y")
                if key == "limit":
                    value = int(value)
                if key in {"cron_hour", "cron_minute"}:
                    value = int(value)
                current[key] = value
            self._config = AppConfig.from_dict(current)
            self.save()
            return deepcopy(self._config)
