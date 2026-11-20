"""SMA Monitoring API (owner OAuth). Set names are approximated from SMA's public sandbox docs."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from sunledger.adapters.base import ApiRequest, Connection, SourceAdapter, month_windows
from sunledger.catalog import Access


class SmaAdapter(SourceAdapter):
    source = "sma"
    access = Access.OWNER_OAUTH
    base_url = "https://monitoring.smaapis.de"

    def plan(self, conn: Connection, start: date, end: date) -> Iterator[ApiRequest]:
        root = f"/monitoring/v1/plants/{conn.external_id}"
        yield ApiRequest("plant", root)
        for lo, _ in month_windows(start, end):
            for set_type in ("EnergyBalance", "BatterySoc"):
                yield ApiRequest(set_type.lower(), f"{root}/measurements/sets/{set_type}/Month",
                                 {"Date": f"{lo:%Y-%m}"})
