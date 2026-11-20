"""Generate the full fixture set: fake API payloads, weather, and SunLedger's own registry data."""

from __future__ import annotations

import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from sunledger.adapters import Connection, adapter_for
from sunledger.adapters.transport import FixtureTransport
from sunledger.catalog import INSTALLERS, SOURCE_ACCESS
from sunledger.config import Settings
from sunledger.synth.fakeapi import FakeApi, service_point_id
from sunledger.synth.fleet import Site, build_fleet, simulate
from sunledger.synth.weather import irradiance_by_postcode


def generate(cfg: Settings) -> dict[str, int]:
    root = cfg.fixtures_dir
    if root.exists():
        shutil.rmtree(root)
    rng = random.Random(cfg.seed)
    sites = build_fleet(cfg.seed, cfg.sites, cfg.as_of, cfg.history_start)
    weather = irradiance_by_postcode(cfg.seed, cfg.history_start, cfg.as_of)

    api = FixtureTransport(root / "api")
    connections: list[Connection] = []
    files = 0
    for site in sites:
        truth = simulate(site, weather[site.loc.postcode], cfg.as_of, rng)
        fake = FakeApi(site, truth, rng.randrange(2**32))
        for conn in _connections(site):
            connections.append(conn)
            adapter = adapter_for(conn.source, api)
            for request in adapter.plan(conn, site.data_start, cfg.as_of):
                api.put(request, fake.respond(conn.source, request))
                files += 1

    _write(root / "reference" / "weather.json", [
        {"postcode": pc, "date": d.isoformat(), "irradiance_kwh_m2": v}
        for pc, series in weather.items() for d, v in series.items()
    ])
    _write(root / "registry" / "installers.json", [
        {"installer_id": i.installer_id, "name": i.name, "state": i.state} for i in INSTALLERS
    ])
    _write(root / "registry" / "sites.json", [_site_record(s) for s in sites])
    _write(root / "registry" / "connections.json", [conn.__dict__ | {
        "access": SOURCE_ACCESS[conn.source].value} for conn in connections])
    _write(root / "registry" / "consent_events.json", _consent_events(sites, rng, cfg.as_of))
    return {"sites": len(sites), "connections": len(connections), "api_payloads": files}


def _connections(site: Site) -> list[Connection]:
    conns = [Connection(f"C-{site.site_id}-OEM", site.site_id, site.source, site.external_id, site.loc.timezone)]
    if site.consents["cdr_meter"]:
        conns.append(Connection(f"C-{site.site_id}-CDR", site.site_id, "cdr", service_point_id(site), site.loc.timezone))
    return conns


def _site_record(s: Site) -> dict[str, Any]:
    """What the owner and installer confirm at onboarding (not available from every API)."""
    return {
        "site_id": s.site_id, "owner_display_name": s.owner, "suburb": s.loc.suburb, "postcode": s.loc.postcode,
        "state": s.loc.state, "latitude": s.loc.lat, "timezone": s.loc.timezone, "installer_id": s.installer_id,
        "brand": s.product.brand, "battery_model": s.product.model, "battery_units": s.units,
        "battery_usable_kwh": round(s.usable_kwh, 2), "warranty_years": s.product.warranty_years,
        "warranty_eol_soh": s.product.warranty_eol_soh, "rte_spec": s.product.rte_spec,
        "pv_kwp": s.pv_kwp, "inverter_kw": s.inverter_kw, "install_date": s.install_date.isoformat(),
        "connected_on": s.data_start.isoformat(), "source": s.source,
        "certificate_recipient": s.certificate_recipient,
    }


def _consent_events(sites: list[Site], rng: random.Random, as_of: date) -> list[dict[str, Any]]:
    events = []
    for s in sites:
        for purpose, granted in s.consents.items():
            at = s.data_start + timedelta(days=0 if purpose == "monitoring" else rng.randint(0, 20))
            if granted:
                events.append(_event(s, purpose, "grant", at))
            elif purpose == "benchmark" and rng.random() < 0.15:  # opted in, later withdrew
                events.append(_event(s, purpose, "grant", at))
                revoked = min(as_of - timedelta(days=1), at + timedelta(days=rng.randint(20, 200)))
                events.append(_event(s, purpose, "revoke", revoked))
    return events


def _event(site: Site, purpose: str, action: str, at: date) -> dict[str, Any]:
    recipient = site.certificate_recipient if purpose == "certificate" else None
    return {"site_id": site.site_id, "purpose": purpose, "action": action,
            "recipient": recipient, "event_at": f"{at}T09:00:00+10:00", "channel": "owner_app"}


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
