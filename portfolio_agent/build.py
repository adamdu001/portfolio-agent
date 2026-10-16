"""CLI: python -m portfolio_agent.build [--raw data/raw] [--out data/processed]"""
from __future__ import annotations

import argparse
from pathlib import Path

from .aliases import ALIASES
from .load import load_all, reconcile
from .portfolio import build_portfolio_summary, build_sector_weights
from .reference import DEFAULT_SECTORS, build_security_reference, load_sectors
from .signals import build_signals

ROOT = Path(__file__).resolve().parents[1]


def build(raw_dir=ROOT / "data/raw", out_dir=ROOT / "data/processed", sectors=DEFAULT_SECTORS,
          aliases=ALIASES) -> dict:
    holdings, file_deltas = load_all(raw_dir)
    ref = build_security_reference(holdings, load_sectors(sectors), aliases)
    tables = {
        "holdings": holdings,
        "security_reference": ref,
        "signals": build_signals(holdings),
        "portfolio_summary": build_portfolio_summary(holdings, ref),
        "sector_weights": build_sector_weights(holdings, ref),
        "reconciliation": reconcile(holdings, file_deltas),
    }
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        import pyarrow  # noqa: F401
        parquet = True
    except ImportError:
        parquet = False
    for name, df in tables.items():
        df.to_csv(out_dir / f"{name}.csv", index=False)
        if parquet:
            df.astype({c: str for c in df.columns if c == "as_of_date"}).to_parquet(out_dir / f"{name}.parquet", index=False)
    return tables


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw", default=ROOT / "data/raw", type=Path)
    ap.add_argument("--out", default=ROOT / "data/processed", type=Path)
    ap.add_argument("--sectors", default=DEFAULT_SECTORS, type=Path)
    a = ap.parse_args(argv)
    t = build(a.raw, a.out, a.sectors)
    for k, v in t.items():
        print(f"{k:20s} {len(v):5d} rows")
    print(f"written to {a.out}")


if __name__ == "__main__":
    main()
