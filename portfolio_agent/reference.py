"""Security reference: CUSIP -> ticker/name/GICS sector (manual sector map)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

GICS_SECTORS = {
    "Energy", "Materials", "Industrials", "Consumer Discretionary", "Consumer Staples",
    "Health Care", "Financials", "Information Technology", "Communication Services",
    "Utilities", "Real Estate",
}
CASH_SECTOR = "Cash"
DEFAULT_SECTORS = Path(__file__).resolve().parents[1] / "data" / "reference" / "sectors.csv"


def load_sectors(path: str | Path = DEFAULT_SECTORS) -> pd.DataFrame:
    s = pd.read_csv(path, dtype=str)
    bad = set(s["gics_sector"]) - GICS_SECTORS - {CASH_SECTOR}
    if bad:
        raise ValueError(f"invalid sectors in {path}: {bad}")
    return s


def build_security_reference(holdings: pd.DataFrame, sectors: pd.DataFrame) -> pd.DataFrame:
    """Latest ticker/name per CUSIP, joined to the sector map. Fails on unmapped securities."""
    latest = (holdings.sort_values("quarter").groupby("cusip", as_index=False)
              .last()[["cusip", "ticker", "name", "is_cash"]])
    ref = latest.merge(sectors[["cusip", "gics_sector"]], on="cusip", how="left")
    ref.loc[ref.is_cash, "gics_sector"] = CASH_SECTOR
    missing = ref[ref.gics_sector.isna()]
    if len(missing):
        raise ValueError(f"no sector for: {missing.ticker.tolist()} - add them to sectors.csv")
    return ref[["cusip", "ticker", "name", "gics_sector"]].sort_values("ticker").reset_index(drop=True)
