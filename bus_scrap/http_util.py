from __future__ import annotations

import gzip
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


def http_get(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 40,
) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/html,*/*",
            **(headers or {}),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read()
        if body[:2] == b"\x1f\x8b":
            try:
                body = gzip.decompress(body)
            except OSError:
                pass
        text = body.decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} em {url}: {text[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Falha de rede ao acessar {url}: {exc.reason}") from exc

    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


def http_get_json(
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 40,
) -> Any:
    return json.loads(http_get(url, headers=headers, timeout=timeout))


def build_url(base: str, params: dict[str, Any]) -> str:
    return f"{base}?{urlencode(params)}"
