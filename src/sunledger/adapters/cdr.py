"""Energy Consumer Data Right: smart-meter interval usage (CDS energy standards).
Via a CDR representative arrangement; grid import/export only, no inverter data."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta

from sunledger.adapters.base import ApiRequest, Connection, SourceAdapter, month_windows
from sunledger.catalog import Access


class CdrEnergyAdapter(SourceAdapter):
    source = "cdr"
    access = Access.CDR
    base_url = "https://cdr.retailer.example/cds-au/v1"
    lookback_days = 120  # interval reads are heavy; meter cross-checks only need recent history

    def plan(self, conn: Connection, start: date, end: date) -> Iterator[ApiRequest]:
        path = f"/energy/electricity/servicepoints/{conn.external_id}/usage"
        for lo, hi in month_windows(max(start, end - timedelta(days=self.lookback_days)), end):
            yield ApiRequest("usage", path, {
                "oldest-date": lo.isoformat(), "newest-date": hi.isoformat(),
                "interval-reads": "FULL", "page": "1",
            })
