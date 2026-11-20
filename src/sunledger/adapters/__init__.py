"""Source adapters, one per data source, behind the `SourceAdapter` contract."""

from __future__ import annotations

from sunledger.adapters.base import ApiRequest, Connection, RawPayload, SourceAdapter, Transport
from sunledger.adapters.cdr import CdrEnergyAdapter
from sunledger.adapters.enphase import EnphaseAdapter
from sunledger.adapters.partner import PartnerBridgeAdapter
from sunledger.adapters.sma import SmaAdapter
from sunledger.adapters.solaredge import SolarEdgeAdapter
from sunledger.adapters.tesla import TeslaAdapter

PARTNER_VENDORS = ("sigenergy", "sungrow", "alphaess", "fronius")


def adapter_for(source: str, transport: Transport) -> SourceAdapter:
    direct = {cls.source: cls for cls in (SolarEdgeAdapter, EnphaseAdapter, TeslaAdapter, SmaAdapter, CdrEnergyAdapter)}
    if source in direct:
        return direct[source](transport)
    if source in PARTNER_VENDORS:
        return PartnerBridgeAdapter(transport, source)
    raise KeyError(f"No adapter for source '{source}'")


__all__ = ["ApiRequest", "Connection", "RawPayload", "SourceAdapter", "Transport", "adapter_for"]
