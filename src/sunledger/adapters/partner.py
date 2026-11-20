"""OEMs not yet connectable: Sigenergy, Alpha ESS, Fronius (partner-gated) and Sungrow (official API, app review).
Simulated as a normalised bridge feed; real shapes depend on each agreement or approved app."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

from sunledger.adapters.base import ApiRequest, Connection, SourceAdapter, month_windows
from sunledger.catalog import SOURCE_ACCESS, Access


class PartnerBridgeAdapter(SourceAdapter):
    base_url = "https://partner-bridge.sunledger.invalid"

    def __init__(self, transport, vendor: str) -> None:
        super().__init__(transport)
        self.vendor = vendor

    @property
    def source(self) -> str:  # type: ignore[override]
        return self.vendor

    @property
    def access(self) -> Access:  # type: ignore[override]
        return SOURCE_ACCESS[self.vendor]

    def plan(self, conn: Connection, start: date, end: date) -> Iterator[ApiRequest]:
        for lo, _ in month_windows(start, end):
            yield ApiRequest("partner_daily", f"/partner/v1/{self.vendor}/plants/{conn.external_id}/daily",
                             {"month": f"{lo:%Y-%m}"})
