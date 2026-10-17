"""End-to-end run: python -m portfolio_agent.run [--extractor stub|openai] [--skip-claims]

1. build      holdings files -> holdings, security reference, signals, portfolio summary, sector weights
2. claims     transcript -> extracted claims -> checked against signals -> claim_checks.csv
3. report     flags.json and report.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .aliases import ALIASES
from .build import build
from .check_claims import run as run_claims
from .extract import stub_extractor
from .reference import DEFAULT_SECTORS
from .report import run as run_report

ROOT = Path(__file__).resolve().parents[1]


class InputError(Exception):
    pass


def run_pipeline(raw_dir=ROOT / "data/raw", transcript=ROOT / "data/transcripts/q1_2026_call.txt",
                 out_dir=ROOT / "data/processed", extractor=stub_extractor, skip_claims=False,
                 sectors=DEFAULT_SECTORS, aliases=ALIASES):
    raw_dir, out_dir, transcript = Path(raw_dir), Path(out_dir), Path(transcript)
    files = sorted(raw_dir.glob("*.xlsx"))
    if len(files) < 2:
        raise InputError(f"need at least 2 holdings .xlsx files in {raw_dir}, found {len(files)}")
    if not skip_claims and not transcript.exists():
        raise InputError(f"transcript not found: {transcript} (use --skip-claims to run without it)")
    out_dir.mkdir(parents=True, exist_ok=True)
    stale = out_dir / "claim_checks.csv"
    if skip_claims and stale.exists():
        stale.unlink()                    # never report claims from an earlier run

    tables = build(raw_dir, out_dir, sectors, aliases=aliases)
    summary = {"quarters": len(tables["portfolio_summary"])}
    if not skip_claims:
        checks, rejected = run_claims(transcript, out_dir, extractor)
        rejected.to_csv(out_dir / "claims_rejected.csv", index=False)
        summary["claims_checked"], summary["claims_rejected"] = len(checks), len(rejected)
    flags = run_report(out_dir)
    summary.update(claim_inconsistencies=len(flags["claim_inconsistencies"]),
                   stock_flags=len(flags["stock_flags"]), sector_flags=len(flags["sector_flags"]),
                   report=str(out_dir / "report.md"), flags_json=str(out_dir / "flags.json"))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default=ROOT / "data/raw", type=Path)
    ap.add_argument("--transcript", default=ROOT / "data/transcripts/q1_2026_call.txt", type=Path)
    ap.add_argument("--out", default=ROOT / "data/processed", type=Path)
    ap.add_argument("--extractor", choices=["stub", "openai"], default="openai")
    ap.add_argument("--skip-claims", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.extractor == "openai" and not a.skip_claims:
            from .llm import openai_extractor
            extractor = openai_extractor()
        else:
            extractor = stub_extractor
        s = run_pipeline(a.raw, a.transcript, a.out, extractor, a.skip_claims)
    except InputError as e:
        sys.exit(f"error: {e}")
    for k, v in s.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
