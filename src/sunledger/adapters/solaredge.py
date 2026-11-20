"""SolarEdge Monitoring API (owner OAuth). Field names follow the published monitoring API."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from sunledger.adapters.base import ApiRequest, Connection, SourceAdapter, month_windows, week_windows
from sunledger.catalog import Access

METERS = "PRODUCTION,CONSUMPTION,SELFCONSUMPTION,FEEDIN,PURCHASED"


class SolarEdgeAdapter(SourceAdapter):
    source = "solaredge"
    access = Access.OWNER_OAUTH
    base_url = "https://monitoringapi.solaredge.com"

    def plan(self, conn: Connection, start: date, end: date) -> Iterator[ApiRequest]:
        site = conn.external_id
        yield ApiRequest("details", f"/site/{site}/details")
        for lo, hi in month_windows(start, end):
            yield ApiRequest("energy_details", f"/site/{site}/energyDetails", {
                "timeUnit": "DAY", "meters": METERS,
                "startTime": f"{lo} 00:00:00", "endTime": f"{hi} 23:59:59",
            })
        for lo, hi in week_windows(start, end):  # storageData allows at most one week per call
            yield ApiRequest("storage_data", f"/site/{site}/storageData", {
                "startTime": f"{lo} 00:00:00", "endTime": f"{hi} 23:59:59",
            })
