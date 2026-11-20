"""Tesla Fleet API energy endpoints (owner OAuth, Powerwall).
Fleet API terms (s5.6.7) prohibit selling or making user data available: payloads stay internal."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from sunledger.adapters.base import ApiRequest, Connection, SourceAdapter, month_windows
from sunledger.catalog import Access


class TeslaAdapter(SourceAdapter):
    source = "tesla"
    access = Access.OWNER_OAUTH
    base_url = "https://fleet-api.prd.na.vn.cloud.tesla.com"

    def plan(self, conn: Connection, start: date, end: date) -> Iterator[ApiRequest]:
        root = f"/api/1/energy_sites/{conn.external_id}"
        yield ApiRequest("site_info", f"{root}/site_info")
        for lo, hi in month_windows(start, end):
            # Daily buckets follow `time_zone`; the offset only bounds the window.
            yield ApiRequest("energy_history", f"{root}/calendar_history", {
                "kind": "energy", "period": "month", "time_zone": conn.timezone,
                "start_date": f"{lo}T00:00:00+10:00", "end_date": f"{hi}T23:59:59+10:00",
            })
            # live_status has no history: SunLedger polls it and archives captures monthly.
            yield ApiRequest("live_status", f"{root}/live_status", {"archive_month": f"{lo:%Y-%m}"})
