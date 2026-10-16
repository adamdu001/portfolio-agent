"""CLI: python -m portfolio_agent.consistency [--runs 5] [--temperature 0]

Runs the extractor several times on the transcript and reports how stable the rows are.
Rows are compared on the fields the checks use: company, action, quarter, multi_quarter.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from .claims import build_claims_table
from .llm import openai_extractor

ROOT = Path(__file__).resolve().parents[1]
KEY_FIELDS = ("company", "action", "quarter", "multi_quarter")


def run_signature(rows):
    return tuple(sorted(tuple(str(r[f]) for f in KEY_FIELDS) for r in rows))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--transcript", default=ROOT / "data/transcripts/q1_2026_call.txt", type=Path)
    ap.add_argument("--runs", default=5, type=int)
    ap.add_argument("--temperature", default=0.0, type=float)
    ap.add_argument("--model", default=None)
    a = ap.parse_args(argv)
    text = a.transcript.read_text()
    extract = openai_extractor(a.model, a.temperature)
    runs, rejected = [], 0
    for _ in range(a.runs):
        rows = extract(text)
        good, bad = build_claims_table(rows, text)
        rejected += len(bad)
        runs.append(good.to_dict("records"))
    row_freq = Counter(tuple(str(r[f]) for f in KEY_FIELDS) for rows in runs for r in rows)
    outputs = Counter(run_signature(rows) for rows in runs)
    print(f"{a.runs} runs, temperature {a.temperature}; rejected rows: {rejected}")
    print(f"distinct full outputs: {len(outputs)}")
    for sig, n in sorted(row_freq.items()):
        print(f"  {n}/{a.runs}  {' | '.join(sig)}")


if __name__ == "__main__":
    main()
