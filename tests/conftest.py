"""Synthetic fixtures mimicking the real file layout (title rows, as-of cell, header, footer junk)."""
import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
REAL_FILES = [RAW / f"h_{q}.xlsx" for q in ("2025Q4", "2026Q1", "2026Q2")]
HEADER = ["Current Period", "Identifier", "Type", "Ticker", "Name", "Security Type", "Shares",
          "Price", "Weight", "∆ Shares", "∆ Weight", "Previous Quarter", "Previous Identifier",
          "Previous Shares", "Previous Weight", "Country"]


def write_fixture(path, as_of, positions, prev=None):
    """positions: list of (cusip, ticker, shares, price). Weights computed incl. cash row."""
    prev = prev or {}
    vals = {c: s * p for c, t, s, p in positions}
    tot = sum(vals.values())
    rows = [["Synthetic Manager"] + [None] * 15, [None] * 16, [as_of] + [None] * 15,
            [None] * 16, [None] * 16, HEADER]
    for c, t, s, p in positions:
        w = round(vals[c] / tot * 100, 2)
        ps, pw = prev.get(c, (None, 0))
        pid = (int(c) if c.isdigit() else c) if ps is not None else None  # mimic lost zeros
        rows.append([dt.datetime(as_of.year, as_of.month, 1), c, "CUSIP", t, f"{t} Inc",
                     "Cash" if c == "CASH" else "Common Stock", s, p, w,
                     s - (ps or 0), round(w - pw, 2), "Prev", pid, ps, pw, "United States"])
    rows += [[None] * 16, ["Comments"] + [None] * 15, [None] * 16, ["End of data"] + [None] * 15]
    pd.DataFrame(rows).to_excel(path, header=False, index=False)


@pytest.fixture
def synthetic_raw(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    q1 = [("000000011", "AAA", 100, 10.0), ("000000022", "BBB", 50, 20.0),
          ("000000033", "CCC", 200, 5.0), ("CASH", "USD", 1000, 1.0)]
    q2 = [("000000011", "AAA", 150, 12.0), ("000000022", "BBB", 50, 18.0),
          ("000000044", "DDD", 10, 50.0), ("CASH", "USD", 500, 1.0)]
    write_fixture(raw / "s1.xlsx", dt.datetime(2025, 12, 31), q1)
    w1 = {c: (s, round(s * p / 4000 * 100, 2)) for c, t, s, p in q1}
    write_fixture(raw / "s2.xlsx", dt.datetime(2026, 3, 31), q2, prev=w1)
    sectors = tmp_path / "sectors.csv"
    sectors.write_text("cusip,ticker,gics_sector\n000000011,AAA,Energy\n000000022,BBB,Financials\n"
                       "000000033,CCC,Utilities\n000000044,DDD,Energy\n")
    return raw, sectors


real = pytest.mark.skipif(not all(f.exists() for f in REAL_FILES),
                          reason="confidential real files not in data/raw/")
