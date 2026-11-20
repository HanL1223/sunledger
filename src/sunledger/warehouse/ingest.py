"""Land raw API payloads and registry data in DuckDB (ELT: parse later, in dbt staging)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb

from sunledger.adapters import Connection, adapter_for
from sunledger.adapters.transport import FixtureTransport
from sunledger.config import Settings

DDL = """
create schema if not exists raw;
create schema if not exists app;
create or replace table raw.api_payloads (
    source varchar, connection_id varchar, site_id varchar, endpoint varchar,
    params json, fetched_at timestamptz, body json
);
create or replace table app.consent_events (
    site_id varchar, purpose varchar, action varchar, recipient varchar,
    event_at timestamptz, channel varchar
);
create or replace table app.certificates (
    certificate_id varchar primary key, site_id varchar, issued_to varchar, issued_at timestamptz,
    valid_until date, content_hash varchar, payload json, revoked boolean default false
);
"""


def ingest(cfg: Settings, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    con.execute(DDL)
    registry = cfg.fixtures_dir / "registry"
    for name in ("sites", "installers", "connections"):
        _load_json_table(con, f"raw.{name}", registry / f"{name}.json")
    _load_json_table(con, "raw.weather_daily", cfg.fixtures_dir / "reference" / "weather.json")
    con.execute("insert into app.consent_events select * from read_json_auto(?)",
                [str(registry / "consent_events.json")])

    transport = FixtureTransport(cfg.fixtures_dir / "api")
    sites = {s["site_id"]: s for s in json.loads((registry / "sites.json").read_text(encoding="utf-8"))}
    count = 0
    for raw in json.loads((registry / "connections.json").read_text(encoding="utf-8")):
        conn = Connection(**{k: raw[k] for k in Connection.__dataclass_fields__})
        start = date.fromisoformat(sites[conn.site_id]["connected_on"])
        batch = [
            (p.source, p.connection_id, p.site_id, p.endpoint, json.dumps(p.params), p.fetched_at, json.dumps(p.body))
            for p in adapter_for(conn.source, transport).extract(conn, start, cfg.as_of)
        ]
        con.executemany("insert into raw.api_payloads values (?, ?, ?, ?, ?, ?, ?)", batch)
        count += len(batch)
    return {"api_payloads": count}


def _load_json_table(con: duckdb.DuckDBPyConnection, table: str, path: Path) -> None:
    con.execute(f"create or replace table {table} as select * from read_json_auto(?)", [str(path)])
