"""Transports: fixture files for the offline demo, HTTPS with a bearer token for production."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sunledger.adapters.base import ApiRequest


class FixtureTransport:
    """Serves recorded (here: synthesised) API responses from disk."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def get(self, request: ApiRequest) -> dict[str, Any]:
        return json.loads((self.root / request.fixture_key).read_text(encoding="utf-8"))

    def put(self, request: ApiRequest, body: dict[str, Any]) -> None:
        path = self.root / request.fixture_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, separators=(",", ":")), encoding="utf-8")


class HttpTransport:
    """Minimal OAuth bearer client; token refresh is delegated to `token_provider`."""

    def __init__(self, base_url: str, token_provider: Callable[[], str], retries: int = 3) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider
        self.retries = retries

    def get(self, request: ApiRequest) -> dict[str, Any]:
        url = f"{self.base_url}{request.path}?{urllib.parse.urlencode(request.params)}"
        for attempt in range(self.retries):
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.token_provider()}"})
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as err:
                if err.code != 429 or attempt == self.retries - 1:
                    raise
                time.sleep(int(err.headers.get("Retry-After", 2 ** attempt)))
        raise RuntimeError("unreachable")
