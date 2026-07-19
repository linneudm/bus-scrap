from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

# ANSI
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_CYAN = "\033[36m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_MAGENTA = "\033[35m"
_BLUE = "\033[34m"

_LEVEL_STYLE = {
    "INFO": (_CYAN, _BOLD),
    "OK": (_GREEN, _BOLD),
    "WARN": (_YELLOW, _BOLD),
    "ERRO": (_RED, _BOLD),
}


def _supports_color() -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if os.getenv("FORCE_COLOR") in {"1", "true", "yes"}:
        return True
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False
    if os.name == "nt":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)) == 0:
                return False
            ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
            return bool(
                kernel32.SetConsoleMode(
                    handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING
                )
            )
        except Exception:
            return False
    return True


class RuntimeLogger:
    """Logs formatados no console (coloridos) e append em log.txt (sem ANSI)."""

    def __init__(self, log_path: Path | None = None) -> None:
        data_dir = Path(os_getenv_data_dir())
        self.log_path = log_path or (data_dir / "log.txt")
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.color = _supports_color()
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                try:
                    reconfigure(encoding="utf-8", errors="replace")
                except Exception:
                    pass

    def _stamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _colorize_console(self, level: str, message: str) -> str:
        stamp = self._stamp()
        plain = f"[{stamp}] [{level}] {message}"
        if not self.color:
            return plain
        fg, weight = _LEVEL_STYLE.get(level, (_RESET, ""))
        return (
            f"{_DIM}[{stamp}]{_RESET} "
            f"{weight}{fg}[{level}]{_RESET} "
            f"{message}"
        )

    def _write(self, level: str, message: str) -> None:
        plain = f"[{self._stamp()}] [{level}] {message}"
        print(self._colorize_console(level, message), flush=True)
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(plain + "\n")

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def success(self, message: str) -> None:
        self._write("OK", message)

    def warn(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERRO", message)

    def section(self, title: str) -> None:
        border = "=" * 60
        if self.color:
            print(f"{_BLUE}{_BOLD}{border}{_RESET}", flush=True)
            self.info(title)
            print(f"{_BLUE}{_BOLD}{border}{_RESET}", flush=True)
        else:
            print(border, flush=True)
            self.info(title)
            print(border, flush=True)

    def help_text(self, text: str) -> None:
        if not self.color:
            print(text, flush=True)
            return

        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                print(flush=True)
                continue
            if stripped.lower().startswith("comandos"):
                print(f"{_MAGENTA}{_BOLD}{stripped}{_RESET}", flush=True)
                continue
            match = re.match(r"^(\s*)(\S.*?)(\s{2,})(.+)$", line)
            if match:
                indent, cmd, spaces, desc = match.groups()
                print(
                    f"{indent}{_GREEN}{cmd}{_RESET}{spaces}{_DIM}{desc}{_RESET}",
                    flush=True,
                )
            else:
                print(f"{_DIM}{line}{_RESET}", flush=True)


def os_getenv_data_dir() -> str:
    return os.getenv("BUS_SCRAP_DATA_DIR", "data")
