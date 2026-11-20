"""Export warehouse outputs into the single-file interactive demo (demo/index.html)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb

from sunledger.catalog import SOURCE_ACCESS, SOURCE_NAMES
from sunledger.config import Settings
from sunledger.evidence import build_pack, narrator, to_html
from sunledger.warehouse.db import connect, rows

HERO_SITE = "S0001"
HERO_INSTALLER = "INS-IRB"
PLACEHOLDER = "/*__SUNLEDGER_DATA__*/null"


def export_demo(cfg: Settings) -> Path:
    with connect(read_only=True) as con:
        data = build_dataset(con, cfg)
    payload = json.dumps(data, separators=(",", ":"), default=_json_default).replace("</", "<\\/")
    page = cfg.demo_template.read_text(encoding="utf-8")
    if PLACEHOLDER not in page:
        raise ValueError("Demo template is missing the data placeholder")
    cfg.demo_html.parent.mkdir(parents=True, exist_ok=True)
    cfg.demo_html.write_text(page.replace(PLACEHOLDER, payload), encoding="utf-8")
    return cfg.demo_html


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value))


def _r(value: float | None, places: int = 3) -> float | None:
    return None if value is None else round(value, places)


def build_dataset(con: duckdb.DuckDBPyConnection, cfg: Settings) -> dict[str, Any]:
    teller = narrator(cfg)
    owner_pack = build_pack(con, HERO_SITE, "warranty_claim", teller)
    insurer_pack = build_pack(con, HERO_SITE, "certificate_summary", teller)
    return {
        "meta": {"as_of": cfg.as_of, "built_at": cfg.as_of,  # pinned so exports are reproducible
                 "seed": cfg.seed, "narrator": owner_pack.narrator, "hero_site": HERO_SITE,
                 "hero_installer": HERO_INSTALLER, "synthetic": True,
                 "platforms": [{"name": SOURCE_NAMES[k], "access": a.value}
                               for k, a in SOURCE_ACCESS.items() if k != "cdr"],
                 "access_mix": {r["access"]: r["n"] for r in rows(con, """
                     select access, count(*) as n from staging.stg_registry__connections
                     where access <> 'cdr' group by 1 order by 1
                 """)}},
        "installers": rows(con, "select * from staging.stg_registry__installers order by installer_name"),
        "sites": _sites(con),
        "faults": rows(con, """
            select site_id, fault_code, severity, round(metric_value, 4) as metric_value, detected_since
            from marts.mart_site_alerts order by site_id, severity_rank, fault_code
        """),
        "catalog": rows(con, "select * from reference.fault_catalog order by fault_code"),
        "weekly": _weekly(con),
        "soh": _soh(con),
        "meter": rows(con, "select * from marts.mart_meter_reconciliation order by site_id"),
        "commissioning": rows(con, "select * from marts.mart_site_commissioning order by site_id"),
        "fleet": rows(con, """
            select site_id, installer_id, priority, round(priority_score, 1) as priority_score,
                   top_fault_code, top_fault_title
            from marts.mart_installer_fleet order by site_id
        """),
        "benchmarks": {
            "synthetic": cfg.synthetic,
            "installers": rows(con, "select * from marts.mart_installer_benchmarks order by installer_name"),
            "brands": rows(con, "select * from marts.mart_brand_benchmarks order by brand"),
        },
        "certificates": [
            {**c, "payload": json.loads(c["payload"])}
            for c in rows(con, """
                select certificate_id, site_id, issued_to, valid_until, content_hash, payload, revoked
                from app.certificates order by site_id
            """)
        ],
        "packs": {
            "owner": {"id": owner_pack.pack_id, "narrator": owner_pack.narrator, "html": to_html(owner_pack)},
            "insurer": {"id": insurer_pack.pack_id, "narrator": insurer_pack.narrator, "html": to_html(insurer_pack)},
        },
    }


def _sites(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    out = []
    for s in rows(con, """
        select d.*, h.*, c.monitoring, c.installer_share, c.benchmark, c.cdr_meter, c.certificate,
               c.certificate_recipient
        from marts.dim_site d
        join marts.mart_site_health h using (site_id)
        join intermediate.int_current_consent c using (site_id)
        order by d.site_id
    """):
        out.append({
            "id": s["site_id"], "owner": s["owner_display_name"], "suburb": s["suburb"], "state": s["state"],
            "postcode": s["postcode"], "installer": s["installer_id"], "brand": s["brand"],
            "model": s["battery_model"], "units": s["battery_units"], "usable": s["battery_usable_kwh"],
            "pv": s["pv_kwp"], "inv": s["inverter_kw"], "dcac": s["dc_ac_ratio"], "installed": s["install_date"],
            "connected": s["connected_on"], "platform": s["platform"], "feed": s["feed"],
            "rebate": s["rebate_era_install"], "score": s["health_score"], "grade": s["health_grade"],
            "points": {k: _r(s[f"{k}_points"], 1) for k in ("generation", "capacity", "efficiency",
                                                            "availability", "fault")},
            "perf": _r(s["perf_ratio_60d"]), "soh": _r(s["soh_now"]), "wsoh": _r(s["warranty_soh_now"]),
            "margin": _r(s["soh_margin"]), "fade": _r(s["soh_slope_per_year"]), "rte": _r(s["rte_now"]),
            "uptime": _r(s["uptime_30d"]), "offline": s["offline_days"], "critical": s["critical_count"],
            "warning": s["warning_count"], "shortfall": _r(s["shortfall_kwh_365"], 0),
            "method": s["capacity_method"],
            "consent": {k: s[k] for k in ("monitoring", "installer_share", "benchmark", "cdr_meter", "certificate")},
            "recipient": s["certificate_recipient"],
        })
    return out


def _weekly(con: duckdb.DuckDBPyConnection) -> dict[str, dict[str, Any]]:
    series: dict[str, dict[str, Any]] = defaultdict(lambda: {"start": None, "pv": [], "exp": []})
    for r in rows(con, """
        select site_id, cast(date_trunc('week', reading_date) as date) as week,
               sum(pv_kwh) as pv, sum(expected_pv_kwh) filter (where is_reporting) as exp,
               count(*) filter (where is_reporting) as days
        from marts.fct_site_daily group by all order by site_id, week
    """):
        s = series[r["site_id"]]
        s["start"] = s["start"] or r["week"]
        has_data = r["days"] >= 3  # average kWh/day per week; mostly-offline weeks become gaps
        s["pv"].append(_r(r["pv"] / r["days"], 2) if has_data else None)
        s["exp"].append(_r(r["exp"] / r["days"], 2) if has_data else None)
    return dict(series)


def _soh(con: duckdb.DuckDBPyConnection) -> dict[str, list[list[Any]]]:
    out: dict[str, list[list[Any]]] = defaultdict(list)
    for r in rows(con, """
        select site_id, strftime(month_start, '%Y-%m') as m, soh, warranty_soh, rte
        from marts.mart_battery_soh_monthly where soh is not null order by site_id, month_start
    """):
        out[r["site_id"]].append([r["m"], _r(r["soh"], 4), _r(r["warranty_soh"], 4), _r(r["rte"], 3)])
    return dict(out)
