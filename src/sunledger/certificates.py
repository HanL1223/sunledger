"""Battery health certificates: the ID is 96 bits of the SHA-256 of the canonical payload,
so tampering breaks the match. Production would add a KMS signature."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import duckdb

from sunledger.config import settings
from sunledger.warehouse.db import rows

SCHEMA = "sunledger.battery-health-certificate/v1"
VALIDITY_DAYS = 90


class ConsentError(PermissionError):
    pass


def canonical_json(payload: dict[str, Any]) -> str:
    """Sorted keys, no whitespace, decimals pre-formatted as strings: reproducible in any language."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def certificate_id(digest: str) -> str:
    return ("SLC-" + "-".join(digest[i:i + 4] for i in range(0, 24, 4))).upper()  # 96 bits


def _dec(value: float | None, places: int = 3) -> str | None:
    return None if value is None else f"{value:.{places}f}"


def build_payload(con: duckdb.DuckDBPyConnection, site_id: str, issued_to: str, issued_on: date) -> dict[str, Any]:
    site = rows(con, """
        with cohort as (
            select h.site_id, d.brand, h.soh_margin
            from marts.mart_site_health h
            join marts.dim_site d using (site_id)
            join intermediate.int_current_consent c using (site_id)
            where c.benchmark or h.site_id = ?
        ),
        ranked as (
            select site_id, percent_rank() over (partition by brand order by soh_margin) as pct,
                   count(*) over (partition by brand) as cohort_size
            from cohort
        )
        select d.*, h.*, r.pct as brand_percentile, r.cohort_size,
               m.days_compared, m.export_diff_pct
        from marts.dim_site d
        join marts.mart_site_health h using (site_id)
        left join ranked r using (site_id)
        left join marts.mart_meter_reconciliation m using (site_id)
        where d.site_id = ?
    """, [site_id, site_id])[0]
    faults = [r["fault_code"] for r in rows(con, """
        select fault_code from marts.mart_site_alerts where site_id = ? order by severity_rank, fault_code
    """, [site_id])]
    coverage = rows(con, """
        select count(*) filter (where is_reporting) as days from marts.fct_site_daily where site_id = ?
    """, [site_id])[0]["days"]
    corroborated = None
    if site["days_compared"]:
        corroborated = abs(site["export_diff_pct"]) <= 0.05

    return {
        "schema": SCHEMA,
        "site_ref": site_id,
        "postcode": site["postcode"],
        "state": site["state"],
        "brand": site["brand"],
        "battery_model": site["battery_model"],
        "nameplate_usable_kwh": _dec(site["battery_usable_kwh"], 1),
        "install_date": site["install_date"].isoformat(),
        "data_as_of": settings().as_of.isoformat(),
        "state_of_health": _dec(site["soh_now"]),
        "warranty_curve_soh": _dec(site["warranty_soh_now"]),
        "soh_margin": _dec(site["soh_margin"]),
        "fade_per_year": _dec(site["soh_slope_per_year"]),
        "capacity_method": site["capacity_method"],
        "round_trip_efficiency": _dec(site["rte_now"]),
        "health_score": int(site["health_score"]),
        "health_grade": site["health_grade"],
        "open_faults": faults,
        "brand_percentile": _dec(site["brand_percentile"], 2) if (site["cohort_size"] or 0) >= 5 else None,
        "days_of_data": int(coverage),
        "meter_corroborated": corroborated,
        "issued_to": issued_to,
        "issued_on": issued_on.isoformat(),
        "valid_until": (issued_on + timedelta(days=VALIDITY_DAYS)).isoformat(),
    }


def issue(con: duckdb.DuckDBPyConnection, site_id: str, issued_to: str, issued_on: date | None = None) -> dict[str, Any]:
    consent = rows(con, "select * from intermediate.int_current_consent where site_id = ?", [site_id])
    if not consent or not consent[0]["certificate"] or consent[0]["certificate_recipient"] != issued_to:
        raise ConsentError(f"Owner of {site_id} has not consented to share a certificate with {issued_to}")

    payload = build_payload(con, site_id, issued_to, issued_on or settings().as_of)
    digest = content_hash(payload)
    cert_id = certificate_id(digest)
    con.execute("""
        insert or replace into app.certificates
        (certificate_id, site_id, issued_to, issued_at, valid_until, content_hash, payload, revoked)
        values (?, ?, ?, ?, ?, ?, ?, false)
    """, [cert_id, site_id, issued_to, datetime.now(UTC), payload["valid_until"], digest, canonical_json(payload)])
    return {"certificate_id": cert_id, "content_hash": digest, "payload": payload}


def verify(con: duckdb.DuckDBPyConnection, cert_id: str, presented: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check a certificate ID against the registry and, optionally, a payload presented by a third party."""
    found = rows(con, "select * from app.certificates where certificate_id = ?", [cert_id.upper()])
    if not found:
        return {"certificate_id": cert_id, "status": "not_found", "valid": False}
    record = found[0]
    consent = rows(con, "select * from intermediate.int_current_consent where site_id = ?", [record["site_id"]])
    stored = json.loads(record["payload"])
    payload = presented if presented is not None else stored
    digest = content_hash(payload)
    checks = {
        "id_matches_hash": certificate_id(digest) == record["certificate_id"],
        "hash_matches_registry": digest == record["content_hash"],
        "not_revoked": not record["revoked"],
        "consent_active": bool(consent) and consent[0]["monitoring"] and consent[0]["certificate"]
        and consent[0]["certificate_recipient"] == record["issued_to"],
        "not_expired": date.fromisoformat(stored["valid_until"]) >= settings().as_of,
    }
    failure = {"id_matches_hash": "tampered", "hash_matches_registry": "tampered",
               "not_revoked": "revoked", "consent_active": "revoked", "not_expired": "expired"}
    status = next((failure[k] for k, ok in checks.items() if not ok), "valid")
    result = {"certificate_id": record["certificate_id"], "status": status, "valid": status == "valid",
              "checks": checks, "issued_to": record["issued_to"], "site_id": record["site_id"]}
    return result | ({"content_hash": digest, "payload": stored} if status == "valid" else {})


def revoke_site(con: duckdb.DuckDBPyConnection, site_id: str) -> int:
    """Revoke every live certificate for a site (owner withdrew certificate or monitoring consent)."""
    return len(con.execute("update app.certificates set revoked = true where site_id = ? and not revoked "
                           "returning certificate_id", [site_id]).fetchall())


def issue_consented(con: duckdb.DuckDBPyConnection) -> int:
    """Issue certificates for every site whose owner has directed one to a named recipient."""
    targets = rows(con, """
        select site_id, certificate_recipient from intermediate.int_current_consent
        where monitoring and certificate and certificate_recipient is not null order by site_id
    """)
    for t in targets:
        issue(con, t["site_id"], t["certificate_recipient"])
    return len(targets)
