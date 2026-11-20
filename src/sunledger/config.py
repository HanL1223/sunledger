"""Runtime settings, resolved from environment variables with demo-friendly defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path


def _project_root() -> Path:
    if home := os.getenv("SUNLEDGER_HOME"):
        return Path(home).resolve()
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    root: Path
    seed: int
    as_of: date
    history_start: date
    sites: int
    llm_model: str
    anthropic_api_key: str | None
    synthetic: bool  # pseudonymise brands in analytic outputs

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def fixtures_dir(self) -> Path:
        return self.data_dir / "fixtures"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "sunledger.duckdb"

    @property
    def dbt_dir(self) -> Path:
        return self.root / "warehouse"

    @property
    def demo_html(self) -> Path:
        return self.root / "demo" / "index.html"

    @property
    def demo_template(self) -> Path:
        return Path(__file__).parent / "web" / "index.template.html"


@cache
def settings() -> Settings:
    return Settings(
        root=_project_root(),
        seed=int(os.getenv("SUNLEDGER_SEED", "20261120")),
        as_of=date.fromisoformat(os.getenv("SUNLEDGER_AS_OF", "2026-11-19")),
        history_start=date.fromisoformat(os.getenv("SUNLEDGER_HISTORY_START", "2025-08-01")),
        sites=int(os.getenv("SUNLEDGER_SITES", "220")),
        llm_model=os.getenv("SUNLEDGER_LLM_MODEL", "claude-sonnet-5-5"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        synthetic=os.getenv("SUNLEDGER_SYNTHETIC", "1") != "0",
    )
