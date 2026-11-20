"""Adapter contract: plan API requests, fetch them, emit raw payloads verbatim.
Adapters only extract; parsing happens in dbt staging, so payloads stay replayable."""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, ClassVar, Protocol

from sunledger.catalog import Access


@dataclass(frozen=True)
class ApiRequest:
    endpoint: str  # logical name used by staging models
    path: str
    params: dict[str, str] = field(default_factory=dict)

    @property
    def fixture_key(self) -> str:
        """Short, stable fixture path: query string hashed to 12 chars (Windows path limits)."""
        query = "&".join(f"{k}={v}" for k, v in sorted(self.params.items()))
        return f"{self.path.strip('/')}/{hashlib.sha256(query.encode()).hexdigest()[:12]}.json"


@dataclass(frozen=True)
class Connection:
    connection_id: str
    site_id: str
    source: str
    external_id: str
    timezone: str


@dataclass(frozen=True)
class RawPayload:
    source: str
    connection_id: str
    site_id: str
    endpoint: str
    params: dict[str, str]
    fetched_at: datetime
    body: dict[str, Any]


class Transport(Protocol):
    def get(self, request: ApiRequest) -> dict[str, Any]: ...


class SourceAdapter(ABC):
    source: ClassVar[str]
    access: ClassVar[Access]
    base_url: ClassVar[str]

    def __init__(self, transport: Transport) -> None:
        self.transport = transport

    @abstractmethod
    def plan(self, conn: Connection, start: date, end: date) -> Iterator[ApiRequest]:
        """Requests needed to backfill [start, end], chunked to the API's window limits."""

    def extract(self, conn: Connection, start: date, end: date) -> Iterator[RawPayload]:
        for request in self.plan(conn, start, end):
            yield RawPayload(
                source=self.source, connection_id=conn.connection_id, site_id=conn.site_id,
                endpoint=request.endpoint, params=request.params, fetched_at=datetime.now(UTC),
                body=self.transport.get(request),
            )


def month_windows(start: date, end: date) -> Iterator[tuple[date, date]]:
    cursor = start
    while cursor <= end:
        nxt = (cursor.replace(day=1) + timedelta(days=32)).replace(day=1)
        yield cursor, min(end, nxt - timedelta(days=1))
        cursor = nxt


def week_windows(start: date, end: date) -> Iterator[tuple[date, date]]:
    cursor = start
    while cursor <= end:
        yield cursor, min(end, cursor + timedelta(days=6))
        cursor += timedelta(days=7)
