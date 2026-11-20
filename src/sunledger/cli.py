"""`sunledger` command line: build, export-demo, serve, evidence-pack, certificate."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def _build(args: argparse.Namespace) -> None:
    if args.sites:
        os.environ["SUNLEDGER_SITES"] = str(args.sites)
    if args.seed:
        os.environ["SUNLEDGER_SEED"] = str(args.seed)
    from sunledger import certificates
    from sunledger.config import settings
    from sunledger.synth.generate import generate
    from sunledger.warehouse.db import connect
    from sunledger.warehouse.dbt import run_models
    from sunledger.warehouse.ingest import ingest

    cfg = settings()
    t0 = time.perf_counter()
    print(f"[1/4] Generating synthetic fleet and API fixtures (seed {cfg.seed}, {cfg.sites} sites)...")
    print("      ", generate(cfg))
    print("[2/4] Extracting via source adapters into DuckDB raw layer...")
    cfg.db_path.unlink(missing_ok=True)
    with connect() as con:
        print("      ", ingest(cfg, con))
    print("[3/4] Running dbt models (staging -> intermediate -> marts)...")
    run_models(cfg)
    print("[4/4] Issuing owner-consented certificates...")
    with connect() as con:
        print(f"       {certificates.issue_consented(con)} certificates issued")
    print(f"Done in {time.perf_counter() - t0:.0f}s -> {cfg.db_path}")


def _models(_: argparse.Namespace) -> None:
    from sunledger.config import settings
    from sunledger.warehouse.dbt import run_models

    run_models(settings())


def _export(_: argparse.Namespace) -> None:
    from sunledger.config import settings
    from sunledger.export import export_demo

    path = export_demo(settings())
    print(f"Demo written to {path} ({path.stat().st_size / 1024:.0f} KB)")


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("sunledger.api:app", host=args.host, port=args.port)


def _pack(args: argparse.Namespace) -> None:
    from sunledger.config import settings
    from sunledger.evidence import build_pack, narrator, to_html_document
    from sunledger.warehouse.db import connect

    with connect(read_only=True) as con:
        pack = build_pack(con, args.site_id, args.kind, narrator(settings()))
    out = Path(args.out or f"{pack.pack_id}.html")
    out.write_text(to_html_document(pack), encoding="utf-8")
    print(f"{pack.title} ({pack.narrator}) -> {out}")


def _certificate(args: argparse.Namespace) -> None:
    from sunledger import certificates
    from sunledger.warehouse.db import connect

    with connect(read_only=args.action == "verify") as con:
        if args.action == "issue":
            result = certificates.issue(con, args.target, args.to)
        else:
            result = certificates.verify(con, args.target)
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(prog="sunledger", description=__doc__)
    sub = parser.add_subparsers(required=True)

    p = sub.add_parser("build", help="generate fixtures, ingest, run dbt, issue certificates")
    p.add_argument("--sites", type=int)
    p.add_argument("--seed", type=int)
    p.set_defaults(func=_build)

    sub.add_parser("models", help="re-run dbt models only").set_defaults(func=_models)
    sub.add_parser("export-demo", help="write demo/index.html from the marts").set_defaults(func=_export)

    p = sub.add_parser("serve", help="run the API")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=_serve)

    p = sub.add_parser("evidence-pack", help="render an evidence pack to HTML")
    p.add_argument("site_id")
    p.add_argument("--kind", choices=["warranty_claim", "certificate_summary"], default="warranty_claim")
    p.add_argument("--out")
    p.set_defaults(func=_pack)

    p = sub.add_parser("certificate", help="issue or verify a battery health certificate")
    p.add_argument("action", choices=["issue", "verify"])
    p.add_argument("target", help="site ID (issue) or certificate ID (verify)")
    p.add_argument("--to", help="recipient named in the owner's consent (issue)")
    p.set_defaults(func=_certificate)

    args = parser.parse_args()
    args.func(args)
