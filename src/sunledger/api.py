"""SunLedger HTTP API (FastAPI). Demo auth is a header stub (X-Demo-Role / X-Demo-Tenant);
production replaces it with OIDC role and tenant claims."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from urllib.parse import urlencode

import duckdb
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from sunledger import certificates
from sunledger.catalog import SOURCE_ACCESS, Access
from sunledger.config import settings
from sunledger.evidence import build_pack, narrator, to_html_document
from sunledger.warehouse.db import rows

Purpose = Literal["monitoring", "installer_share", "benchmark", "cdr_meter", "certificate"]

# Read-only scopes only: SunLedger never requests control scopes such as Tesla's energy_cmds.
OAUTH = {
    "tesla": ("https://auth.tesla.com/oauth2/v3/authorize", ["openid", "offline_access", "energy_device_data"]),
    "enphase": ("https://api.enphaseenergy.com/oauth/authorize", []),
    "solaredge": ("<issued at SolarEdge developer onboarding>", ["monitoring:read"]),
    "sma": ("<issued at SMA developer onboarding>", ["monitoring:read"]),
}

_state: dict[str, duckdb.DuckDBPyConnection] = {}


@asynccontextmanager
async def lifespan(_: FastAPI):
    _state["db"] = duckdb.connect(str(settings().db_path))
    yield
    _state.pop("db").close()


app = FastAPI(title="SunLedger API", version="0.1.0", lifespan=lifespan,
              description="Independent health records for home solar + battery systems (demo).")


def db() -> Iterator[duckdb.DuckDBPyConnection]:
    cursor = _state["db"].cursor()  # one cursor per request: thread-safe
    try:
        yield cursor
    finally:
        cursor.close()


Db = Annotated[duckdb.DuckDBPyConnection, Depends(db)]


@dataclass(frozen=True)
class Principal:
    role: Literal["owner", "installer", "underwriter"]
    tenant: str  # owner: site_id · installer: installer_id · underwriter: organisation name


def principal(x_demo_role: Annotated[str | None, Header()] = None,
              x_demo_tenant: Annotated[str | None, Header()] = None) -> Principal:
    """DEMO ONLY: trusts headers. Not authentication."""
    if x_demo_role not in ("owner", "installer", "underwriter") or not x_demo_tenant:
        raise HTTPException(401, "Send X-Demo-Role (owner|installer|underwriter) and X-Demo-Tenant headers")
    return Principal(x_demo_role, x_demo_tenant)


Caller = Annotated[Principal, Depends(principal)]


def _authorise(caller: Principal, *roles: str, tenant: str | None = None) -> None:
    if caller.role not in roles or (tenant is not None and caller.tenant != tenant):
        raise HTTPException(403, f"{caller.role} '{caller.tenant}' may not access this resource")


class ConsentChange(BaseModel):
    purpose: Purpose
    action: Literal["grant", "revoke"]
    recipient: str | None = None


class CertificateRequest(BaseModel):
    site_id: str
    issued_to: str


class PresentedCertificate(BaseModel):
    payload: dict[str, Any]


def _consent(con: duckdb.DuckDBPyConnection, site_id: str) -> dict[str, Any]:
    found = rows(con, "select * from intermediate.int_current_consent where site_id = ?", [site_id])
    if not found:
        raise HTTPException(404, f"Unknown site {site_id}")
    return found[0]


def _require(con: duckdb.DuckDBPyConnection, site_id: str, purpose: str) -> None:
    if not _consent(con, site_id)[purpose]:
        raise HTTPException(403, f"Owner has not granted '{purpose}' for {site_id}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "as_of": settings().as_of.isoformat()}


@app.get("/v1/sources")
def sources() -> list[dict[str, Any]]:
    gated = (Access.PARTNER_GATED, Access.DEVELOPER_PORTAL)
    return [{"source": s, "access": a.value, "self_serve": a not in gated} for s, a in SOURCE_ACCESS.items()]


@app.post("/v1/connect/{source}/authorize")
def authorize(source: str, redirect_uri: str = "http://localhost:8000/callback") -> dict[str, Any]:
    access = SOURCE_ACCESS.get(source)
    if access is None:
        raise HTTPException(404, f"Unknown source {source}")
    if access == Access.PARTNER_GATED:
        raise HTTPException(409, f"{source} requires an OEM partner agreement; connect smart-meter data via CDR meanwhile")
    if access == Access.DEVELOPER_PORTAL:
        raise HTTPException(409, f"{source} has an official developer API, but the integration is not live yet; "
                                 "connect smart-meter data via CDR meanwhile")
    if source == "cdr":
        return {"source": source, "flow": "CDR consent via accredited data recipient (redirect to retailer)"}
    url, scopes = OAUTH[source]
    query = urlencode({"response_type": "code", "client_id": "sunledger-demo", "redirect_uri": redirect_uri,
                       "scope": " ".join(scopes), "state": "demo-state"})
    return {"source": source, "authorize_url": f"{url}?{query}", "scopes": scopes, "read_only": True}


@app.get("/v1/sites/{site_id}/consents")
def get_consents(site_id: str, con: Db, caller: Caller) -> dict[str, Any]:
    _authorise(caller, "owner", tenant=site_id)
    return _consent(con, site_id)


@app.post("/v1/sites/{site_id}/consents")
def change_consent(site_id: str, change: ConsentChange, con: Db, caller: Caller) -> dict[str, Any]:
    _authorise(caller, "owner", tenant=site_id)
    _consent(con, site_id)
    if change.purpose == "certificate" and change.action == "grant" and not change.recipient:
        raise HTTPException(422, "Certificate consent must name a recipient")
    con.execute("insert into app.consent_events values (?, ?, ?, ?, ?, 'api')",
                [site_id, change.purpose, change.action, change.recipient, datetime.now(UTC)])
    if change.action == "revoke" and change.purpose in ("certificate", "monitoring"):
        certificates.revoke_site(con, site_id)
    return _consent(con, site_id)  # consent-gated marts are views: effective immediately


@app.get("/v1/sites/{site_id}/dashboard")
def dashboard(site_id: str, con: Db, caller: Caller) -> dict[str, Any]:
    _authorise(caller, "owner", tenant=site_id)
    _require(con, site_id, "monitoring")
    return {
        "site": rows(con, "select * from marts.dim_site where site_id = ?", [site_id])[0],
        "health": rows(con, "select * from marts.mart_site_health where site_id = ?", [site_id])[0],
        "soh_monthly": rows(con, "select * from marts.mart_battery_soh_monthly where site_id = ? order by 2", [site_id]),
        "generation_weekly": rows(con, """
            select cast(date_trunc('week', reading_date) as date) as week_start,
                   sum(pv_kwh) as pv_kwh, sum(expected_pv_kwh) filter (where is_reporting) as expected_kwh
            from marts.fct_site_daily where site_id = ? group by 1 order by 1
        """, [site_id]),
    }


@app.get("/v1/sites/{site_id}/alerts")
def alerts(site_id: str, con: Db, caller: Caller) -> list[dict[str, Any]]:
    _authorise(caller, "owner", tenant=site_id)
    _require(con, site_id, "monitoring")
    return rows(con, "select * from marts.mart_site_alerts where site_id = ? order by severity_rank", [site_id])


@app.post("/v1/sites/{site_id}/evidence-pack", response_model=None)
def evidence_pack(site_id: str, con: Db, caller: Caller, kind: Literal["warranty_claim", "certificate_summary"] = "warranty_claim",
                  fmt: Annotated[Literal["json", "html"], Query(alias="format")] = "json") -> Any:
    _authorise(caller, "owner", tenant=site_id)
    _require(con, site_id, "monitoring")
    pack = build_pack(con, site_id, kind, narrator(settings()))
    return HTMLResponse(to_html_document(pack)) if fmt == "html" else pack.to_dict()


@app.get("/v1/installers/{installer_id}/fleet")
def fleet(installer_id: str, con: Db, caller: Caller) -> list[dict[str, Any]]:
    _authorise(caller, "installer", tenant=installer_id)
    return rows(con, """
        select * from marts.mart_installer_fleet where installer_id = ?
        order by priority, priority_score desc
    """, [installer_id])


@app.get("/v1/installers/{installer_id}/sites/{site_id}/commissioning")
def commissioning(installer_id: str, site_id: str, con: Db, caller: Caller) -> dict[str, Any]:
    _authorise(caller, "installer", tenant=installer_id)
    _require(con, site_id, "installer_share")
    found = rows(con, "select * from marts.mart_site_commissioning where site_id = ? and installer_id = ?",
                 [site_id, installer_id])
    if not found:
        raise HTTPException(404, "No commissioning record (site not connected at handover, or not your install)")
    return found[0]


@app.post("/v1/certificates")
def issue_certificate(req: CertificateRequest, con: Db, caller: Caller) -> dict[str, Any]:
    _authorise(caller, "owner", tenant=req.site_id)  # only the owner directs a certificate
    try:
        return certificates.issue(con, req.site_id, req.issued_to)
    except certificates.ConsentError as err:
        raise HTTPException(403, str(err)) from err


def _verified(result: dict[str, Any], caller: Principal) -> dict[str, Any]:
    """Anyone may check status; only the named recipient or the owner sees the contents."""
    entitled = (caller.role == "underwriter" and caller.tenant == result.get("issued_to")) or (
        caller.role == "owner" and caller.tenant == result.get("site_id"))
    hidden = {"site_id", "issued_to"} | (set() if entitled else {"payload", "content_hash"})
    return {k: v for k, v in result.items() if k not in hidden}


@app.get("/v1/certificates/{certificate_id}/verify")
def verify_certificate(certificate_id: str, con: Db, caller: Caller) -> dict[str, Any]:
    return _verified(certificates.verify(con, certificate_id), caller)


@app.post("/v1/certificates/{certificate_id}/verify")
def verify_presented(certificate_id: str, presented: PresentedCertificate, con: Db, caller: Caller) -> dict[str, Any]:
    return _verified(certificates.verify(con, certificate_id, presented.payload), caller)


@app.get("/v1/benchmarks/installers")
def installer_benchmarks(con: Db, caller: Caller) -> dict[str, Any]:
    _authorise(caller, "installer", "underwriter")
    return {"synthetic": settings().synthetic,
            "installers": rows(con, "select * from marts.mart_installer_benchmarks order by installer_name")}


@app.get("/v1/benchmarks/brands")
def brand_benchmarks(con: Db, caller: Caller) -> dict[str, Any]:
    _authorise(caller, "installer", "underwriter")
    return {"synthetic": settings().synthetic,  # brands pseudonymised (Brand A-H) when synthetic
            "brands": rows(con, "select * from marts.mart_brand_benchmarks order by brand")}
