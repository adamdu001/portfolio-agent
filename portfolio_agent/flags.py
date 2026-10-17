"""Collect the flagged evidence from the tables into one JSON-ready structure.

Pure selection and formatting, no model: every item keeps its source numbers and an id, and
carries a template-written `summary` sentence built only from those numbers.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pandas as pd

VERB = {"initiate": "initiated a new position in", "add": "added to", "hold": "held",
        "trim": "trimmed", "exit": "exited"}
SECTOR_HHI_FLOOR = 10000 / 11   # perfectly even spread over the 11 GICS sectors


def _py(v: Any) -> Any:
    """numpy/pandas scalar -> plain Python; NaN/NA -> None."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v.is_integer() and abs(v) > 1000:
        return int(v)
    return round(v, 4) if isinstance(v, float) else v


def _rec(row: pd.Series, cols: List[str]) -> Dict[str, Any]:
    out = {c: _py(row[c]) for c in cols}
    return {c: (int(v) if c.endswith("_row") and v is not None else v) for c, v in out.items()}


def _signed(x: float, nd: int = 2) -> str:
    return f"{x:+.{nd}f}"


# ---- stock-level flags -------------------------------------------------------------------
STOCK_COLS = ["cusip", "ticker", "from_q", "to_q", "action", "shares_prev", "shares_curr",
              "d_shares", "d_shares_pct", "w_prev", "w_curr", "d_w", "active_w", "passive_w",
              "streak", "prev_source_row", "curr_source_row"]


def stock_summary(r: Dict[str, Any]) -> str:
    step = f"{r['from_q']} to {r['to_q']}"
    a = r["action"]
    if a == "initiate":
        return (f"{r['ticker']}: initiated a new position ({step}): 0 to {r['shares_curr']:,.0f} "
                f"shares, weight 0.00% to {r['w_curr']:.2f}%.")
    if a == "exit":
        return (f"{r['ticker']}: exited the position ({step}): {r['shares_prev']:,.0f} to 0 shares, "
                f"weight {r['w_prev']:.2f}% to 0.00%.")
    s = (f"{r['ticker']}: {VERB[a]} the position ({step}): shares {r['shares_prev']:,.0f} to "
         f"{r['shares_curr']:,.0f} ({_signed(r['d_shares_pct'], 1)}%); weight {r['w_prev']:.2f}% to "
         f"{r['w_curr']:.2f}% ({_signed(r['d_w'])} pp), of which trading {_signed(r['active_w'])} pp "
         f"and price moves {_signed(r['passive_w'])} pp.")
    if r["streak"] and r["streak"] >= 2:
        s += f" {r['streak']} consecutive steps in this direction."
    return s


def stock_flags(signals: pd.DataFrame) -> List[Dict[str, Any]]:
    m = signals[signals.is_material & ~signals.is_cash].copy()
    m["_first"] = ~m.action.isin(["initiate", "exit"])          # initiates and exits first
    m["_abs"] = m.active_w.abs().fillna(m.d_w.abs())
    m = m.sort_values(["from_q", "_first", "_abs"], ascending=[True, True, False])
    out = []
    for _, row in m.iterrows():
        rec = _rec(row, STOCK_COLS)
        rec = {"id": f"ST-{rec['ticker']}-{rec['to_q']}", **rec}
        rec["summary"] = stock_summary(rec)
        out.append(rec)
    return out


# ---- sector and portfolio flags ----------------------------------------------------------
def sector_flags(sector_weights: pd.DataFrame) -> List[Dict[str, Any]]:
    t = sector_weights[sector_weights.is_tilt].copy()
    t["_abs"] = t.d_weight_pp.abs()
    t = t.sort_values(["quarter", "_abs"], ascending=[True, False])
    out = []
    for _, r in t.iterrows():
        prev_w = r.weight_pct - r.d_weight_pp
        rec = {"id": f"SE-{r.gics_sector}-{r.quarter}", **_rec(
            r, ["quarter", "gics_sector", "weight_pct", "d_weight_pp", "n_positions"])}
        rec["weight_prev_pct"] = round(float(prev_w), 4)
        rec["summary"] = (f"{r.gics_sector}: weight {'rose' if r.d_weight_pp > 0 else 'fell'} from "
                          f"{prev_w:.2f}% to {r.weight_pct:.2f}% ({_signed(r.d_weight_pp)} pp) in "
                          f"{r.quarter}; {int(r.n_positions)} position(s).")
        out.append(rec)
    return out


def concentration(portfolio_summary: pd.DataFrame) -> List[Dict[str, Any]]:
    cols = ["quarter", "n_positions", "hhi", "effective_n", "top10_weight_pct", "n_sectors",
            "sector_hhi", "top_sector", "top_sector_weight", "sectors_in", "sectors_out"]
    out, prev = [], None
    for _, r in portfolio_summary.sort_values("quarter").iterrows():
        rec = {"id": f"PS-{r.quarter}", **_rec(r, cols), "sector_hhi_floor": round(SECTOR_HHI_FLOOR, 1)}
        rec["sector_hhi_change"] = None if prev is None else round(float(r.sector_hhi - prev), 1)
        rec["summary"] = (f"{r.quarter}: sector HHI {r.sector_hhi:.0f} (floor {SECTOR_HHI_FLOOR:.0f}); "
                          f"top sector {r.top_sector} at {r.top_sector_weight:.2f}% of the portfolio; "
                          f"stock HHI {r.hhi:.0f}."
                          + ("" if rec["sector_hhi_change"] is None else
                             f" Sector HHI {_signed(rec['sector_hhi_change'], 0)} vs the previous quarter."))
        prev = r.sector_hhi
        out.append(rec)
    return out


# ---- claim inconsistencies ---------------------------------------------------------------
CLAIM_COLS = ["claim_id", "source_id", "company", "ticker", "quote", "action", "quarter", "quarter_basis",
              "multi_quarter", "duration_phrase", "quote_multiple_occurrences", "verdict", "reason", "observed_action", "from_q",
              "to_q", "shares_prev", "shares_curr", "d_shares_pct", "active_w", "streak",
              "prev_source_row", "curr_source_row"]


def claim_flags(claim_checks: Optional[pd.DataFrame]) -> List[Dict[str, Any]]:
    if claim_checks is None:
        return []
    out = []
    for _, r in claim_checks[claim_checks.verdict != "consistent"].iterrows():
        rec = {"id": f"CL-{r.claim_id}", **_rec(r, CLAIM_COLS)}
        rec["quote_locations"] = [
            {"offset": o, "paragraph": int(p)} for o, p in
            zip(str(r.offsets).split(";"), str(r.paragraphs).split(";")) if o]
        rec["summary"] = f"{r.company}: the manager said {r.action} ({r.quarter}). {r.reason}"
        out.append(rec)
    return out


def build_flags(signals: pd.DataFrame, sector_weights: pd.DataFrame,
                portfolio_summary: pd.DataFrame,
                claim_checks: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    return {
        "claim_inconsistencies": claim_flags(claim_checks),
        "claims_checked": None if claim_checks is None else int(len(claim_checks)),
        "stock_flags": stock_flags(signals),
        "sector_flags": sector_flags(sector_weights),
        "concentration": concentration(portfolio_summary),
    }
