"""CLI: python -m portfolio_agent.report  (run build, then check_claims, first)

Writes data/processed/flags.json (the structured evidence) and report.md (rendered from it).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .flags import build_flags
from .render import render_markdown

ROOT = Path(__file__).resolve().parents[1]


def run(processed_dir=ROOT / "data/processed"):
    d = Path(processed_dir)
    rd = lambda n, **kw: pd.read_csv(d / f"{n}.csv", **kw)
    signals = rd("signals", dtype={"cusip": str})
    signals["is_cash"] = signals.is_cash.astype(bool)
    signals["is_material"] = signals.is_material.astype(bool)
    sw = rd("sector_weights")
    sw["is_tilt"] = sw.is_tilt.astype(bool)
    claims = rd("claim_checks", dtype={"cusip": str}) if (d / "claim_checks.csv").exists() else None
    flags = build_flags(signals, sw, rd("portfolio_summary"), claims)
    (d / "flags.json").write_text(json.dumps(flags, indent=2))
    (d / "report.md").write_text(render_markdown(flags))
    return flags


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processed", default=ROOT / "data/processed", type=Path)
    a = ap.parse_args(argv)
    f = run(a.processed)
    print(f"{len(f['claim_inconsistencies'])} claim inconsistencies, {len(f['stock_flags'])} stock flags, "
          f"{len(f['sector_flags'])} sector tilts -> {a.processed}/flags.json, report.md")


if __name__ == "__main__":
    main()
