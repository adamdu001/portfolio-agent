"""Security reference: CUSIP -> ticker/name/GICS sector (manual sector map)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .aliases import aliases_for

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


def build_security_reference(holdings: pd.DataFrame, sectors: pd.DataFrame,
                             aliases: dict | None = None) -> pd.DataFrame:
    """Latest ticker/name per CUSIP, joined to the sector map and name variants.

    Fails on securities with no sector, on non-cash securities missing from `aliases`
    (when given), and when two securities share a name variant.
    """
    latest = (holdings.sort_values("quarter").groupby("cusip", as_index=False)
              .last()[["cusip", "ticker", "name", "is_cash"]])
    ref = latest.merge(sectors[["cusip", "gics_sector"]], on="cusip", how="left")
    ref.loc[ref.is_cash, "gics_sector"] = CASH_SECTOR
    missing = ref[ref.gics_sector.isna()]
    if len(missing):
        raise ValueError(f"no sector for: {missing.ticker.tolist()} - add them to sectors.csv")
    if aliases is not None:
        absent = ref[~ref.is_cash & ~ref.cusip.isin(aliases)]
        if len(absent):
            raise ValueError(f"no aliases entry for: {absent.ticker.tolist()} - add them to aliases.py")
    ref["alias_list"] = [[] if c else aliases_for(u, t, n, aliases)
                         for u, t, n, c in zip(ref.cusip, ref.ticker, ref.name, ref.is_cash)]
    seen = {}
    for u, lst in zip(ref.cusip, ref.alias_list):
        for a in lst:
            if seen.setdefault(a, u) != u:
                raise ValueError(f"alias {a!r} belongs to two securities: {seen[a]} and {u}")
    ref["aliases"] = ref.alias_list.map("|".join)
    return (ref[["cusip", "ticker", "name", "gics_sector", "aliases"]]
            .sort_values("ticker").reset_index(drop=True))
