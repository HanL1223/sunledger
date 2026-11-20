"""Run the dbt project programmatically (no shell scripts, works the same on Windows)."""

from __future__ import annotations

import json
import os

from dbt.cli.main import dbtRunner

from sunledger.config import Settings


def run_models(cfg: Settings, select: str | None = None) -> None:
    os.environ["SUNLEDGER_DB"] = str(cfg.db_path)
    args = [
        "build", "--project-dir", str(cfg.dbt_dir), "--profiles-dir", str(cfg.dbt_dir),
        "--target-path", str(cfg.data_dir / "dbt_target"), "--log-path", str(cfg.data_dir / "dbt_logs"),
        "--vars", json.dumps({"as_of": cfg.as_of.isoformat(), "synthetic": cfg.synthetic}), "--quiet",
    ]
    if select:
        args += ["--select", select]
    result = dbtRunner().invoke(args)
    if not result.success:
        raise RuntimeError(f"dbt run failed: {result.exception or 'see dbt logs'}")
