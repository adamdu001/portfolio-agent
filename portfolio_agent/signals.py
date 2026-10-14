"""Quarter-over-quarter position signals with active/passive weight decomposition."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MaterialityConfig:
    # Tunable defaults (not derived from data). 25% is a common "resized" rule of thumb;
    # 0.5 percentage points ≈ a fifth of a typical ~2–3% position in this fund.
    d_shares_pct: float = 25.0     # |% change in shares|
    active_w: float = 0.5          # |active weight change| in percentage points
    always_material: tuple = ("initiate", "exit")


DIRECTION = {"initiate": 1, "add": 1, "hold": 0, "trim": -1, "exit": -1}
# Active/passive split only for continuing positions; labels alone flag initiate/exit.
SPLIT_ACTIONS = ("add", "trim", "hold")


def classify(prev: float, curr: float) -> str:
    if prev == 0 and curr > 0:
        return "initiate"
    if prev > 0 and curr == 0:
        return "exit"
    if curr > prev:
        return "add"
    if curr < prev:
        return "trim"
    return "hold"


def pair_signals(prev: pd.DataFrame, curr: pd.DataFrame, cfg: MaterialityConfig) -> pd.DataFrame:
    keep = ["cusip", "ticker", "shares", "price", "weight_pct", "source_row", "is_cash"]
    m = prev[keep].merge(curr[keep], on="cusip", how="outer", suffixes=("_p", "_c"))
    m["ticker"] = m["ticker_c"].fillna(m["ticker_p"])
    m["is_cash"] = m["is_cash_c"].fillna(m["is_cash_p"]).astype(bool)
    sp = m["shares_p"].fillna(0.0)
    sc = m["shares_c"].fillna(0.0)
    action = pd.Series([classify(a, b) for a, b in zip(sp, sc)], index=m.index)
    # New price when present; exits have no current file price (NaN, not imputed).
    px_curr = m["price_c"]
    # Do-nothing portfolio: old shares at new prices. Exits lack a new price in the files,
    # so their old price is used only in the denominator for continuing stocks.
    px_for_held = px_curr.fillna(m["price_p"])
    held_val = sp * px_for_held
    total = held_val.sum()
    split = action.isin(SPLIT_ACTIONS)
    w_unchanged = np.where(split, held_val / total * 100, np.nan)
    w_prev = m["weight_pct_p"].fillna(0.0)
    w_curr = m["weight_pct_c"].fillna(0.0)
    out = pd.DataFrame({
        "cusip": m["cusip"], "ticker": m["ticker"], "is_cash": m["is_cash"],
        "from_q": prev["quarter"].iloc[0], "to_q": curr["quarter"].iloc[0],
        "shares_prev": sp, "shares_curr": sc, "d_shares": sc - sp,
        "d_shares_pct": np.where(sp > 0, (sc - sp) / sp.where(sp > 0) * 100, np.nan),
        "action": action,
        "w_prev": w_prev, "w_curr": w_curr,
        "d_w": w_curr - w_prev,
        "price_curr": px_curr,
        "w_unchanged": w_unchanged,
        "active_w": np.where(split, w_curr - w_unchanged, np.nan),
        "passive_w": np.where(split, w_unchanged - w_prev, np.nan),
    })
    # Material = (i) initiate/exit by label, or (ii) significant add/trim via share % or active_w.
    # NaN active_w compares False, so initiate/exit rely on always_material only.
    out["is_material"] = (
        (out.d_shares_pct.abs() >= cfg.d_shares_pct)
        | (out.active_w.abs() >= cfg.active_w)
        | out.action.isin(cfg.always_material)
    ) & ~out.is_cash
    out["prev_source_row"] = m["source_row_p"].astype("Int64")
    out["curr_source_row"] = m["source_row_c"].astype("Int64")
    return out


def build_signals(holdings: pd.DataFrame, cfg: MaterialityConfig | None = None) -> pd.DataFrame:
    cfg = cfg or MaterialityConfig()
    qs = sorted(holdings["quarter"].unique())
    parts = [pair_signals(holdings[holdings.quarter == a], holdings[holdings.quarter == b], cfg)
             for a, b in zip(qs, qs[1:])]
    if not parts:
        return pd.DataFrame()
    s = pd.concat(parts, ignore_index=True).sort_values(["cusip", "from_q"])
    streaks, last = [], {}
    for cusip, act, fq in zip(s.cusip, s.action, s.from_q):
        d = DIRECTION[act]
        prev_d, prev_n = last.get(cusip, (0, 0))
        n = 0 if d == 0 else (prev_n + 1 if d == prev_d else 1)
        last[cusip] = (d, n)
        streaks.append(n)
    s["streak"] = streaks
    cols = ["cusip", "ticker", "from_q", "to_q", "shares_prev", "shares_curr", "d_shares",
            "d_shares_pct", "action", "w_prev", "w_curr", "d_w", "w_unchanged", "active_w",
            "passive_w", "price_curr", "is_cash", "is_material", "streak",
            "prev_source_row", "curr_source_row"]
    return s[cols].sort_values(["from_q", "ticker"]).reset_index(drop=True)
