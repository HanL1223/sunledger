"""Pluggable narrators. The LLM only writes prose from supplied facts; numbers come from the data."""

from __future__ import annotations

import json
from typing import Any, Protocol

from sunledger.config import Settings

SYSTEM_PROMPT = """You write short, factual summaries for SunLedger evidence packs about Australian home
solar and battery systems. Use ONLY the facts in the JSON provided. Never invent numbers, dates,
legal outcomes or product claims. Plain English, calm and professional, Australian spelling.
At most 150 words, no headings, no bullet points, no legal advice."""

AUDIENCE = {
    "warranty_claim": "the system owner, who will send this pack to their installer and the manufacturer",
    "certificate_summary": "an insurance or green-lending underwriter assessing the battery's condition",
}


class Narrator(Protocol):
    name: str

    def summarise(self, kind: str, facts: dict[str, Any]) -> str: ...


class TemplateNarrator:
    """Deterministic offline narrator: the demo default."""

    name = "template"

    def summarise(self, kind: str, facts: dict[str, Any]) -> str:
        s, h = facts["site"], facts["health"]
        lead = (f"This {s['brand']} {s['battery_model']} ({s['battery_usable_kwh']:.1f} kWh usable) was installed "
                f"on {s['install_date']} at a home in {s['suburb']} {s['state']} by {s['installer_name']}.")
        battery = (f" As of {facts['as_of']}, its measured state of health is {h['soh_now']:.1%} against "
                   f"{h['warranty_soh_now']:.1%} expected by the warranty curve for its age "
                   f"({h['soh_margin'] * 100:+.1f} points), based on {facts['coverage_days']} days of monitoring data.")
        faults = facts["faults"]
        if faults:
            listed = "; ".join(f"{f['title'].lower()} (since {f['detected_since'] or 'detection'})" for f in faults)
            issues = f" SunLedger has detected: {listed}."
        else:
            issues = " No open faults are detected."
        meter = facts.get("meter")
        corroboration = (f" Grid export reported by the system matches the independent smart meter within "
                         f"{abs(meter['export_diff_pct']):.1%} over {meter['days_compared']} days."
                         if meter and meter.get("days_compared") else "")
        close = {
            "warranty_claim": " The owner requests that the installer and manufacturer assess the battery under "
                              "the manufacturer's warranty and the consumer guarantees in the Australian Consumer Law.",
            "certificate_summary": f" Overall health score {h['health_score']:.0f}/100 (grade {h['health_grade']}).",
        }[kind]
        return lead + battery + issues + corroboration + close


class AnthropicNarrator:
    def __init__(self, api_key: str, model: str) -> None:
        import anthropic  # optional dependency: `uv sync --extra llm`

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.name = f"anthropic:{model}"

    def summarise(self, kind: str, facts: dict[str, Any]) -> str:
        message = self.client.messages.create(
            model=self.model, max_tokens=600, system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": (
                f"Audience: {AUDIENCE[kind]}.\nWrite the summary paragraph for this pack.\n\n"
                f"FACTS:\n{json.dumps(facts, default=str, indent=1)}"
            )}],
        )
        return "".join(block.text for block in message.content if block.type == "text").strip()


def narrator(cfg: Settings) -> Narrator:
    if cfg.anthropic_api_key:
        try:
            return AnthropicNarrator(cfg.anthropic_api_key, cfg.llm_model)
        except ImportError:
            pass
    return TemplateNarrator()
