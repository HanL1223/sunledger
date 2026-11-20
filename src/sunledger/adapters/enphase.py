"""Enphase Enlighten API v4 (owner OAuth; Watt plan allows 1k hits/month)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

from sunledger.adapters.base import ApiRequest, Connection, SourceAdapter, week_windows
from sunledger.catalog import Access


class EnphaseAdapter(SourceAdapter):
    source = "enphase"
    access = Access.OWNER_OAUTH
    base_url = "https://api.enphaseenergy.com"

    def plan(self, conn: Connection, start: date, end: date) -> Iterator[ApiRequest]:
        root = f"/api/v4/systems/{conn.external_id}"
        span = {"start_date": start.isoformat(), "end_date": end.isoformat()}
        yield ApiRequest("summary", f"{root}/summary")
        yield ApiRequest("energy_lifetime", f"{root}/energy_lifetime", span)
        yield ApiRequest("energy_import_lifetime", f"{root}/energy_import_lifetime", span)
        yield ApiRequest("energy_export_lifetime", f"{root}/energy_export_lifetime", span)
        for lo, _ in week_windows(start, end):
            epoch = int(datetime(lo.year, lo.month, lo.day, tzinfo=UTC).timestamp())
            yield ApiRequest("battery_telemetry", f"{root}/telemetry/battery",
                             {"start_at": str(epoch), "granularity": "week"})
