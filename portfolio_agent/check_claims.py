"""CLI: python -m portfolio_agent.check_claims [--transcript data/transcripts/q1_2026_call.txt]

Reads the processed tables written by `portfolio_agent.build`, extracts claims from the transcript
(stub extractor until a real model is plugged in), and writes data/processed/claim_checks.csv.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .claims import build_claims_table
from .extract import Extractor, stub_extractor
from .verdicts import ClaimCheckConfig, check_claims

ROOT = Path(__file__).resolve().parents[1]


def run(transcript_path, processed_dir=ROOT / "data/processed", extractor: Extractor = stub_extractor,
        cfg: ClaimCheckConfig = ClaimCheckConfig()):
    transcript = Path(transcript_path).read_text()
    processed = Path(processed_dir)
    ref = pd.read_csv(processed / "security_reference.csv", dtype=str)
    sig = pd.read_csv(processed / "signals.csv", dtype={"cusip": str})
    claims, rejected = build_claims_table(extractor(transcript), transcript)
    checks = check_claims(claims, ref, sig, cfg)
    checks.to_csv(processed / "claim_checks.csv", index=False)
    return checks, rejected


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transcript", default=ROOT / "data/transcripts/q1_2026_call.txt", type=Path)
    ap.add_argument("--processed", default=ROOT / "data/processed", type=Path)
    a = ap.parse_args(argv)
    checks, rejected = run(a.transcript, a.processed)
    print(checks[["claim_id", "company", "action", "quarter", "verdict", "reason"]].to_string(index=False))
    if len(rejected):
        print(f"\n{len(rejected)} model row(s) rejected:\n{rejected[['company', 'problems']].to_string(index=False)}")


if __name__ == "__main__":
    main()
