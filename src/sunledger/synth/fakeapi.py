"""Fake upstream APIs: render simulated truth into payloads shaped like each real API.
Simplified: two telemetry samples per day (15:00 peak, 06:00 trough); fixed +10:00 offset."""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from itertools import accumulate
from typing import Any

from sunledger.adapters.base import ApiRequest
from sunledger.synth.fleet import DayTruth, Site

AEST = timedelta(hours=10)
IMPORT_SHAPE = [0.6] * 12 + [1.6] * 6 + [0.8] * 16 + [2.4] * 10 + [1.0] * 4
EXPORT_SHAPE = [0.0] * 18 + [max(0.0, 1 - abs(i - 6.5) / 7) for i in range(14)] + [0.0] * 16


def _norm(shape: list[float]) -> list[float]:
    total = sum(shape)
    return [w / total for w in shape]


IMPORT_W, EXPORT_W = _norm(IMPORT_SHAPE), _norm(EXPORT_SHAPE)


def service_point_id(site: Site) -> str:
    """Opaque CDR service point identifier (CDR never exposes the raw NMI)."""
    return f"SP{site.site_id}{site.external_id[-4:]}"


def _epoch(day: date, local_hour: int) -> int:
    return int((datetime.combine(day, time(local_hour), tzinfo=UTC) - AEST).timestamp())


def _span(params: dict[str, str], lo_key: str, hi_key: str) -> tuple[date, date]:
    return date.fromisoformat(params[lo_key][:10]), date.fromisoformat(params[hi_key][:10])


def _month(value: str) -> tuple[date, date]:
    lo = date.fromisoformat(f"{value}-01")
    hi = (lo + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return lo, hi


class FakeApi:
    """Answers every request an adapter plans for one site connection."""

    def __init__(self, site: Site, truth: list[DayTruth], seed: int) -> None:
        self.site = site
        self.days = {t.day: t for t in truth}
        self.rng = random.Random(seed)
        self.charged = dict(zip(self.days, accumulate(t.charge_kwh * 1000 for t in truth)))
        self.discharged = dict(zip(self.days, accumulate(t.discharge_kwh * 1000 for t in truth)))

    def respond(self, source: str, request: ApiRequest) -> dict[str, Any]:
        family = "partner" if request.endpoint == "partner_daily" else source
        handler: Callable[[ApiRequest], dict[str, Any]] = getattr(self, f"_{family}_{request.endpoint}")
        return handler(request)

    def _between(self, lo: date, hi: date, reporting_only: bool = True) -> list[DayTruth]:
        days = (self.days.get(lo + timedelta(n)) for n in range((hi - lo).days + 1))
        return [t for t in days if t and (t.reporting or not reporting_only)]

    def _pack_wh(self, t: DayTruth) -> int:
        return round(t.capacity_kwh * 1000 * self.rng.gauss(1, 0.008))

    # SolarEdge -------------------------------------------------------------------------
    def _solaredge_details(self, req: ApiRequest) -> dict[str, Any]:
        s = self.site
        return {"details": {
            "id": int(s.external_id), "name": f"{s.owner} home", "status": "Active", "peakPower": s.pv_kwp,
            "installationDate": s.install_date.isoformat(), "type": "Optimizers & Inverters",
            "location": {"country": "Australia", "city": s.loc.suburb, "zip": s.loc.postcode,
                         "timeZone": s.loc.timezone, "countryCode": "AU"},
            "primaryModule": {"manufacturerName": "Generic", "modelName": "440W mono", "maximumPower": 440.0},
            "publicSettings": {"isPublic": False},
        }}

    def _solaredge_energy_details(self, req: ApiRequest) -> dict[str, Any]:
        lo, hi = _span(req.params, "startTime", "endTime")
        rows = self._between(lo, hi, reporting_only=False)
        series = {
            "Production": lambda t: t.pv_kwh,
            "FeedIn": lambda t: t.export_kwh,
            "Purchased": lambda t: t.import_kwh,
            "SelfConsumption": lambda t: t.pv_kwh - t.export_kwh,
            "Consumption": lambda t: t.pv_kwh - t.export_kwh + t.import_kwh - t.charge_kwh + t.discharge_kwh,
        }
        meters = [{"type": name, "values": [
            {"date": f"{t.day} 00:00:00", **({"value": round(fn(t) * 1000, 1)} if t.reporting else {})}
            for t in rows
        ]} for name, fn in series.items()]
        return {"energyDetails": {"timeUnit": "DAY", "unit": "Wh", "meters": meters}}

    def _solaredge_storage_data(self, req: ApiRequest) -> dict[str, Any]:
        lo, hi = _span(req.params, "startTime", "endTime")
        telemetries = []
        for t in self._between(lo, hi):
            prev = self.days.get(t.day - timedelta(1))
            if prev and prev.reporting:  # morning sample closes the previous evening's discharge
                telemetries.append(self._se_sample(t.day, 6, prev.soc_trough, prev, prev))
            telemetries.append(self._se_sample(t.day, 15, t.soc_peak, t, prev))
        s = self.site
        return {"storageData": {"batteryCount": 1, "batteries": [{
            "nameplate": round(s.usable_kwh * 1000), "serialNumber": s.serial,
            "modelNumber": "HB-97-DEMO", "telemetryCount": len(telemetries), "telemetries": telemetries,
        }]}}

    def _se_sample(self, day: date, hour: int, soc: float, t: DayTruth, prev: DayTruth | None) -> dict[str, Any]:
        # Counters at 15:00 include today's charge but only discharges up to last night.
        return {
            "timeStamp": f"{day} {hour:02d}:00:00", "power": round(900 * self.rng.random(), 1),
            "batteryState": 3 if hour == 15 else 4,
            "lifeTimeEnergyCharged": round(self.charged[t.day]),
            "lifeTimeEnergyDischarged": round(self.discharged[prev.day]) if prev else 0,
            "fullPackEnergyAvailable": self._pack_wh(t), "internalTemp": round(self.rng.uniform(18, 34)),
            "ACGridCharging": 0.0, "stateOfCharge": round(soc, 1),
        }

    # Enphase ---------------------------------------------------------------------------
    def _enphase_summary(self, req: ApiRequest) -> dict[str, Any]:
        s = self.site
        return {
            "system_id": int(s.external_id), "size_w": round(s.pv_kwp * 1000), "status": "normal",
            "operational_at": _epoch(s.install_date, 12), "battery_capacity_wh": round(s.usable_kwh * 1000),
            "source": "microinverters", "modules": round(s.pv_kwp * 1000 / 440),
        }

    def _enphase_lifetime(self, req: ApiRequest, key: str, fn: Callable[[DayTruth], float]) -> dict[str, Any]:
        lo, hi = _span(req.params, "start_date", "end_date")
        values = []
        for n in range((hi - lo).days + 1):
            t = self.days.get(lo + timedelta(n))
            values.append(round(fn(t) * 1000) if t and t.reporting else 0)
        return {"system_id": int(self.site.external_id), "start_date": lo.isoformat(), key: values,
                "meta": {"status": "normal", "last_report_at": _epoch(hi, 23)}}

    def _enphase_energy_lifetime(self, req: ApiRequest) -> dict[str, Any]:
        return self._enphase_lifetime(req, "production", lambda t: t.pv_kwh)

    def _enphase_energy_import_lifetime(self, req: ApiRequest) -> dict[str, Any]:
        return self._enphase_lifetime(req, "import", lambda t: t.import_kwh)

    def _enphase_energy_export_lifetime(self, req: ApiRequest) -> dict[str, Any]:
        return self._enphase_lifetime(req, "export", lambda t: t.export_kwh)

    def _enphase_battery_telemetry(self, req: ApiRequest) -> dict[str, Any]:
        start = datetime.fromtimestamp(int(req.params["start_at"]), UTC).date()
        units = self.site.units
        intervals = []
        for t in self._between(start, start + timedelta(6)):
            intervals.append({"end_at": _epoch(t.day, 15),
                              "charge": {"enwh": round(t.charge_kwh * 1000), "devices_reporting": units},
                              "discharge": {"enwh": 0, "devices_reporting": units},
                              "soc": {"percent": round(t.soc_peak), "devices_reporting": units}})
            intervals.append({"end_at": _epoch(t.day + timedelta(1), 6),
                              "charge": {"enwh": 0, "devices_reporting": units},
                              "discharge": {"enwh": round(t.discharge_kwh * 1000), "devices_reporting": units},
                              "soc": {"percent": round(t.soc_trough), "devices_reporting": units}})
        return {"system_id": int(self.site.external_id), "granularity": "week", "total_devices": units,
                "start_at": int(req.params["start_at"]), "items": "intervals", "intervals": intervals,
                "last_reported_aggregate_soc": f"{round(intervals[-1]['soc']['percent']) if intervals else 0}%"}

    # Tesla -----------------------------------------------------------------------------
    def _tesla_site_info(self, req: ApiRequest) -> dict[str, Any]:
        s = self.site
        return {"response": {
            "id": s.external_id, "site_name": f"{s.owner} home",
            "installation_date": f"{s.install_date}T10:00:00+10:00", "nameplate_power": round(s.inverter_kw * 1000),
            "nameplate_energy": round(s.usable_kwh * 1000), "battery_count": s.units,
            "backup_reserve_percent": round(s.reserve * 100),
            "components": {"battery": True, "solar": True, "grid": True, "battery_type": "ac_powerwall"},
        }}

    def _tesla_energy_history(self, req: ApiRequest) -> dict[str, Any]:
        lo, hi = _span(req.params, "start_date", "end_date")
        series = []
        for t in self._between(lo, hi):
            house = t.pv_kwh - t.export_kwh - t.charge_kwh
            wh = {
                "solar_energy_exported": t.pv_kwh, "grid_energy_imported": t.import_kwh,
                "grid_energy_exported_from_solar": t.export_kwh, "grid_energy_exported_from_battery": 0,
                "battery_energy_exported": t.discharge_kwh, "battery_energy_imported_from_solar": t.charge_kwh,
                "battery_energy_imported_from_grid": 0, "consumer_energy_imported_from_grid": t.import_kwh,
                "consumer_energy_imported_from_solar": house, "consumer_energy_imported_from_battery": t.discharge_kwh,
            }
            series.append({"timestamp": f"{t.day}T00:00:00+10:00", **{k: round(v * 1000) for k, v in wh.items()}})
        return {"response": {"serial_number": self.site.serial, "period": "month", "time_series": series}}

    def _tesla_live_status(self, req: ApiRequest) -> dict[str, Any]:
        lo, hi = _month(req.params["archive_month"])
        captures = []
        for t in self._between(lo, hi):
            prev = self.days.get(t.day - timedelta(1))
            if prev and prev.reporting:
                captures.append(self._tesla_capture(t.day, 6, prev.soc_trough, prev))
            captures.append(self._tesla_capture(t.day, 15, t.soc_peak, t))
        return {"captures": captures}

    def _tesla_capture(self, day: date, hour: int, soc: float, t: DayTruth) -> dict[str, Any]:
        pack = self._pack_wh(t)
        return {"captured_at": f"{day}T{hour:02d}:00:00+10:00", "response": {
            "solar_power": round(self.rng.uniform(1500, 4500)) if hour == 15 else 0,
            "percentage_charged": round(soc, 2), "energy_left": round(pack * soc / 100), "total_pack_energy": pack,
            "battery_power": 0, "load_power": round(self.rng.uniform(300, 900)), "grid_status": "Active",
            "grid_power": 0, "island_status": "on_grid", "storm_mode_active": False,
            "timestamp": f"{day}T{hour:02d}:00:00+10:00",
        }}

    # SMA -------------------------------------------------------------------------------
    def _sma_plant(self, req: ApiRequest) -> dict[str, Any]:
        s = self.site
        return {"plantId": s.external_id, "name": f"{s.owner} home", "timezone": s.loc.timezone,
                "peakPower": round(s.pv_kwp * 1000), "location": {"postCode": s.loc.postcode, "country": "AU"}}

    def _sma_set(self, req: ApiRequest, set_type: str, fn: Callable[[DayTruth], dict]) -> dict[str, Any]:
        lo, hi = _month(req.params["Date"])
        s = self.site
        return {"plant": {"plantId": s.external_id, "name": f"{s.owner} home", "timezone": s.loc.timezone},
                "setType": set_type, "resolution": "Month",
                "set": [{"time": f"{t.day}T00:00:00", **fn(t)} for t in self._between(lo, hi)]}

    def _sma_energybalance(self, req: ApiRequest) -> dict[str, Any]:
        return self._sma_set(req, "EnergyBalance", lambda t: {
            "pvGeneration": round(t.pv_kwh * 1000), "batteryCharging": round(t.charge_kwh * 1000),
            "batteryDischarging": round(t.discharge_kwh * 1000), "gridFeedIn": round(t.export_kwh * 1000),
            "externalGridConsumption": round(t.import_kwh * 1000),
        })

    def _sma_batterysoc(self, req: ApiRequest) -> dict[str, Any]:
        return self._sma_set(req, "BatterySoc", lambda t: {
            "batteryStateOfChargeMax": round(t.soc_peak, 1), "batteryStateOfChargeMin": round(t.soc_trough, 1),
        })

    # Partner bridge ----------------------------------------------------------------------
    def _partner_partner_daily(self, req: ApiRequest) -> dict[str, Any]:
        lo, hi = _month(req.params["month"])
        return {"vendor": self.site.source, "plant_id": self.site.external_id, "month": req.params["month"],
                "records": [{
                    "date": t.day.isoformat(), "pv_kwh": round(t.pv_kwh, 3),
                    "grid_import_kwh": round(t.import_kwh, 3), "grid_export_kwh": round(t.export_kwh, 3),
                    "battery_charge_kwh": round(t.charge_kwh, 3), "battery_discharge_kwh": round(t.discharge_kwh, 3),
                    "soc_max_pct": round(t.soc_peak, 1), "soc_min_pct": round(t.soc_trough, 1),
                } for t in self._between(lo, hi)]}

    # Energy CDR --------------------------------------------------------------------------
    def _cdr_usage(self, req: ApiRequest) -> dict[str, Any]:
        lo, hi = _span(req.params, "oldest-date", "newest-date")
        reads = []
        for t in self._between(lo, hi, reporting_only=False):  # the meter reads regardless of inverter comms
            for suffix, total, weights in (("E1", t.import_kwh, IMPORT_W), ("B1", t.export_kwh, EXPORT_W)):
                intervals = [round(total * w * self.rng.gauss(1, 0.04), 3) if w else 0.0 for w in weights]
                reads.append({
                    "servicePointId": service_point_id(self.site), "registerId": suffix, "registerSuffix": suffix,
                    "meterID": f"MTR{self.site.external_id}", "controlledLoad": False,
                    "readStartDate": t.day.isoformat(), "readEndDate": t.day.isoformat(),
                    "unitOfMeasure": "KWH", "readUType": "intervalRead",
                    "intervalRead": {"readIntervalLength": 30, "aggregateValue": round(sum(intervals), 3),
                                     "intervalReads": intervals, "readQualities": []},
                })
        return {"data": {"reads": reads}, "links": {"self": req.path},
                "meta": {"totalRecords": len(reads), "totalPages": 1}}
