"""Evidence packs: warranty / ACL claim pack for owners, certificate summary for underwriters."""

from __future__ import annotations

import hashlib
import html
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

import duckdb

from sunledger.config import settings
from sunledger.evidence.llm import Narrator, TemplateNarrator
from sunledger.warehouse.db import rows

Kind = Literal["warranty_claim", "certificate_summary"]

REGULATORS = {
    "VIC": "Consumer Affairs Victoria", "NSW": "NSW Fair Trading",
    "QLD": "Office of Fair Trading Queensland", "SA": "Consumer and Business Services SA",
}


@dataclass
class Section:
    heading: str
    paragraphs: list[str] = field(default_factory=list)
    bullets: list[str] = field(default_factory=list)
    table: list[list[str]] = field(default_factory=list)  # first row is the header


@dataclass
class EvidencePack:
    pack_id: str
    kind: Kind
    title: str
    site_id: str
    generated_at: str
    narrator: str
    sections: list[Section]
    facts: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def gather_facts(con: duckdb.DuckDBPyConnection, site_id: str) -> dict[str, Any]:
    site = rows(con, "select * from marts.dim_site where site_id = ?", [site_id])
    if not site:
        raise KeyError(site_id)
    health = rows(con, "select * from marts.mart_site_health where site_id = ?", [site_id])[0]
    meter = rows(con, "select * from marts.mart_meter_reconciliation where site_id = ?", [site_id])
    commissioning = rows(con, "select * from marts.mart_site_commissioning where site_id = ?", [site_id])
    return {
        "as_of": settings().as_of.isoformat(),
        "site": site[0],
        "health": health,
        "faults": rows(con, """
            select fault_code, severity, category, title, metric_value, threshold, detected_since,
                   owner_explanation, installer_action, warranty_relevant
            from marts.mart_site_alerts where site_id = ? order by severity_rank, fault_code
        """, [site_id]),
        "soh_monthly": rows(con, """
            select month_start, soh, warranty_soh, rte, capacity_method
            from marts.mart_battery_soh_monthly where site_id = ? and soh is not null order by month_start
        """, [site_id]),
        "meter": meter[0] if meter else None,
        "commissioning": commissioning[0] if commissioning else None,
        "coverage_days": rows(con, "select count(*) filter (where is_reporting) as n from marts.fct_site_daily "
                                   "where site_id = ?", [site_id])[0]["n"],
    }


def build_pack(con: duckdb.DuckDBPyConnection, site_id: str, kind: Kind, narrator: Narrator) -> EvidencePack:
    facts = gather_facts(con, site_id)
    try:
        summary, used = narrator.summarise(kind, facts), narrator.name
    except Exception:  # LLM outage must never block an owner's claim pack
        summary, used = TemplateNarrator().summarise(kind, facts), "template (fallback)"

    sections = [Section("Summary", paragraphs=[summary]), _system_section(facts), _findings_section(facts),
                _capacity_section(facts)]
    if facts["meter"] and facts["meter"]["days_compared"]:
        sections.append(_meter_section(facts))
    if kind == "warranty_claim":
        sections += [_rights_section(facts), _request_section(facts), _letter_section(facts)]
    sections.append(_method_section(facts))

    title = {"warranty_claim": "Battery warranty & consumer guarantee evidence pack",
             "certificate_summary": "Battery health certificate summary"}[kind]
    body = json.dumps({"facts": facts, "sections": [asdict(s) for s in sections]}, default=str, sort_keys=True)
    pack_id = "SLP-" + hashlib.sha256(body.encode()).hexdigest()[:12].upper()
    return EvidencePack(pack_id, kind, title, site_id, datetime.now(UTC).isoformat(timespec="seconds"), used,
                        sections, json.loads(json.dumps(facts, default=str)))


def _pct(value: float | None, places: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{places}f}%"


def _system_section(f: dict[str, Any]) -> Section:
    s = f["site"]
    return Section("System details", table=[
        ["Item", "Detail"],
        ["Location", f"{s['suburb']} {s['state']} {s['postcode']}"],
        ["Installer", s["installer_name"]],
        ["Battery", f"{s['brand']} {s['battery_model']} x{s['battery_units']} ({s['battery_usable_kwh']:.1f} kWh usable)"],
        ["Solar array / inverter", f"{s['pv_kwp']:.1f} kWp / {s['inverter_kw']:.1f} kW (DC:AC {s['dc_ac_ratio']:.2f})"],
        ["Installed", str(s["install_date"])],
        ["Monitored since", str(s["connected_on"])],
        ["Data source", s["platform"]],
        ["Warranty", f"{s['warranty_years']} years, {s['warranty_eol_soh']:.0%} capacity retained at end"],
    ])


METHOD = {"oem_reported": "reported by the battery", "estimated": "estimated, assumed ±3 pts (unvalidated)"}


def _measured(fault: dict[str, Any], f: dict[str, Any]) -> tuple[str, str]:
    v, h = fault["metric_value"], f["health"]
    method = METHOD.get(h["capacity_method"], "method unknown")
    return {
        "OFFLINE": (f"{v:.0f} days without data", "3+ days"),
        "DATA_GAPS": (f"{_pct(v)} of days reported (30 days)", "below 90%"),
        "STRING_UNDERPERFORMANCE": (f"output {_pct(v)} of expected (60 days)", "below 82%"),
        "SEASONAL_SHADING": (f"winter output {_pct(v)} of summer level", "below 85%"),
        "INVERTER_CLIPPING": (f"sunny-day output {_pct(v)} of typical-day level", "below 92%"),
        "ARRAY_OVERSIZED": (f"DC:AC ratio {v:.2f}", "above 1.33"),
        "CAPACITY_BELOW_WARRANTY": (f"{_pct(h['soh_now'])} ({method}) vs {_pct(h['warranty_soh_now'])} "
                                    "warranty curve", "3+ points below curve"),
        "CAPACITY_SHORT_AT_HANDOVER": (f"{_pct(v)} of quoted usable capacity in the first 60 days ({method})",
                                       "below 95%"),
        "CAPACITY_FADE_ACCELERATED": (f"losing {abs(v) * 100:.1f}% of capacity per year", "faster than 4.5%/yr"),
        "RTE_DEGRADED": (f"round-trip efficiency {_pct(v)}", "below 82% (spec ~90%)"),
    }[fault["fault_code"]]


def _findings_section(f: dict[str, Any]) -> Section:
    if not f["faults"]:
        return Section("Findings", paragraphs=["No open faults detected."])
    table = [["Finding", "Measured", "Threshold", "Since", "Severity"]]
    for fault in f["faults"]:
        measured, threshold = _measured(fault, f)
        table.append([fault["title"], measured, threshold, str(fault["detected_since"] or "ongoing"),
                      fault["severity"]])
    return Section("Findings", table=table, bullets=[f"{x['title']}: {x['owner_explanation']}" for x in f["faults"]])


def _capacity_section(f: dict[str, Any]) -> Section:
    months = f["soh_monthly"]
    if not months:
        return Section("Battery capacity record", paragraphs=["Insufficient deep-cycle data to estimate capacity yet."])
    method = months[-1]["capacity_method"]
    note = ("Capacity is the full-pack energy reported by the battery management system, read daily via the "
            "manufacturer API." if method == "oem_reported" else
            "Capacity is estimated (not reported by the battery) from energy discharged across the "
            "state-of-charge swing on deep-cycle days, corrected for round-trip efficiency; uncertainty "
            "is assumed to be about ±3 percentage points (not yet validated).")
    table = [["Month", "Measured capacity", "Warranty curve", "Gap"]]
    for m in months:
        table.append([str(m["month_start"])[:7], _pct(m["soh"]), _pct(m["warranty_soh"]),
                      f"{(m['soh'] - m['warranty_soh']) * 100:+.1f} pts"])
    return Section("Battery capacity record (monthly median, % of rated usable capacity)", paragraphs=[note],
                   table=table)


def _meter_section(f: dict[str, Any]) -> Section:
    m = f["meter"]
    text = (f"Over {m['days_compared']} days, grid export reported by the inverter ({m['inverter_export_kwh']:.0f} kWh) "
            f"was compared with the retailer's smart-meter data obtained under the Consumer Data Right "
            f"({m['meter_export_kwh']:.0f} kWh): a difference of {m['export_diff_pct'] * 100:+.1f}%.")
    return Section("Independent corroboration (smart meter)", paragraphs=[text])


def _rights_section(f: dict[str, Any]) -> Section:
    regulator = REGULATORS.get(f["site"]["state"], "your state consumer protection agency")
    return Section("Your rights (summary, not legal advice)", bullets=[
        "Under the Australian Consumer Law (Competition and Consumer Act 2010 (Cth), Schedule 2), goods must be of "
        "acceptable quality, including durable for their price and description (s 54), and fit for any purpose "
        "you made known (s 55).",
        "Installation is a service and must be performed with due care and skill (s 60).",
        "These consumer guarantees apply in addition to the manufacturer's warranty, which must be honoured (s 59), "
        "and cannot be excluded by contract.",
        "If a guarantee is not met, you can ask the supplier for a remedy (ss 259-261 for goods, s 267 for "
        "services); for a major failure you may choose a refund or replacement. Manufacturers can also be liable "
        "(s 271).",
        f"If your installer does not resolve the issue, you can contact {regulator}.",
    ])


def _request_section(f: dict[str, Any]) -> Section:
    asks = ["Acknowledge this report within 5 business days.",
            "Arrange an inspection and a written diagnosis of the findings above."]
    if any(x["fault_code"] in ("CAPACITY_BELOW_WARRANTY", "RTE_DEGRADED") for x in f["faults"]):
        asks.append("Lodge a warranty claim with the battery manufacturer, attaching this pack, and confirm the "
                    "claim reference.")
    if any(x["fault_code"] == "CAPACITY_SHORT_AT_HANDOVER" for x in f["faults"]):
        asks.append("Check the system's configuration against the usable capacity on the quote and confirm in writing.")
    asks.append("Propose a remedy (repair or replacement) and a timeframe in writing.")
    return Section("What the owner is asking for", bullets=asks)


def _letter_section(f: dict[str, Any]) -> Section:
    s, h = f["site"], f["health"]
    issues = ", ".join(x["title"].lower() for x in f["faults"]) or "the attached findings"
    return Section("Draft message to installer", paragraphs=[
        f"Dear {s['installer_name']},",
        f"My {s['brand']} {s['battery_model']}, installed by you on {s['install_date']} at my home in {s['suburb']}, "
        f"is showing {issues}. Independent monitoring data shows its usable capacity at {_pct(h['soh_now'])} "
        + ("of the usable capacity on my quote, and it has been short since installation." if h["short_at_handover"]
           else f"of rated, below the {_pct(h['warranty_soh_now'])} the manufacturer's warranty curve allows at this age."),
        "Please find the evidence pack attached. I would appreciate it if you could arrange an inspection and "
        + ("check the system against the capacity you quoted" if h["short_at_handover"]
           else "lodge a warranty claim with the manufacturer on my behalf")
        + ", and let me know the next steps within 5 business days.",
        "Kind regards,",
        s["owner_display_name"],
    ])


def _method_section(f: dict[str, Any]) -> Section:
    return Section("Method, data provenance and limitations", bullets=[
        "Data was collected read-only, with the owner's consent, from the manufacturer's monitoring API; SunLedger "
        "cannot control or change the system.",
        "Expected solar output uses daily irradiance for the postcode and the array size; thresholds are listed "
        "with each finding.",
        "Warranty curve assumes linear fade to the end-of-warranty capacity; check the exact terms of your "
        "manufacturer's warranty.",
        f"Data as of {f['as_of']}. This pack summarises measurements and is not legal advice.",
    ])


def to_html(pack: EvidencePack) -> str:
    """Self-contained, printable HTML fragment (scoped styles)."""
    e = html.escape
    parts = [f'<article class="sl-pack"><header><p class="sl-kicker">SunLedger · {e(pack.pack_id)}</p>',
             f"<h1>{e(pack.title)}</h1>",
             f'<p class="sl-meta">Site {e(pack.site_id)} · data as of {e(pack.facts["as_of"])} · '
             f"generated {e(pack.generated_at[:10])} · narrative: {e(pack.narrator)}</p></header>"]
    for section in pack.sections:
        parts.append(f"<section><h2>{e(section.heading)}</h2>")
        parts += [f"<p>{e(p)}</p>" for p in section.paragraphs]
        if section.table:
            head, *body = section.table
            parts.append("<table><thead><tr>" + "".join(f"<th>{e(c)}</th>" for c in head) + "</tr></thead><tbody>")
            parts += ["<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in body]
            parts.append("</tbody></table>")
        if section.bullets:
            parts.append("<ul>" + "".join(f"<li>{e(b)}</li>" for b in section.bullets) + "</ul>")
        parts.append("</section>")
    parts.append(f'<footer>Pack ID {e(pack.pack_id)} is a SHA-256 fingerprint of the facts and text above.</footer>'
                 "</article>")
    return "".join(parts)


PACK_CSS = """
.sl-pack{font:14px/1.55 system-ui,sans-serif;color:#1d2a2a;max-width:820px;margin:auto}
.sl-pack h1{font-size:22px;margin:.2em 0}.sl-pack h2{font-size:15px;margin:1.4em 0 .4em;color:#0f4c45}
.sl-pack .sl-kicker,.sl-pack .sl-meta,.sl-pack footer{color:#5b6b6a;font-size:12px}
.sl-pack table{border-collapse:collapse;width:100%;margin:.5em 0}
.sl-pack th,.sl-pack td{border-bottom:1px solid #dfe6e4;padding:4px 8px;text-align:left;font-size:13px}
.sl-pack footer{margin-top:2em;border-top:1px solid #dfe6e4;padding-top:.6em}
"""


def to_html_document(pack: EvidencePack) -> str:
    return (f"<!DOCTYPE html><html lang='en-AU'><head><meta charset='utf-8'><title>{html.escape(pack.title)}</title>"
            f"<style>{PACK_CSS}</style></head><body>{to_html(pack)}</body></html>")
