"""Portfolio-level summary and sector weights."""
from __future__ import annotations

import pandas as pd


def summarise_quarter(q: pd.DataFrame, prev: pd.DataFrame | None) -> dict:
    nc = q[~q.is_cash]
    w = nc.weight_pct
    norm = w / w.sum()
    hhi = float((norm ** 2).sum() * 10000)
    top = nc.loc[w.idxmax()]
    row = dict(
        quarter=q.quarter.iloc[0], as_of_date=q.as_of_date.iloc[0],
        n_positions=len(nc), cash_pct=float(q.loc[q.is_cash, "weight_pct"].sum()),
        total_weight_pct=float(q.weight_pct.sum()),
        hhi=hhi, effective_n=10000 / hhi,
        top10_weight_pct=float(w.nlargest(10).sum()),
        max_position_ticker=top.ticker, max_position_weight=float(top.weight_pct),
    )
    if prev is None:
        ins = outs = None
    else:
        pc, cc = set(prev.loc[~prev.is_cash, "cusip"]), set(nc.cusip)
        ins = sorted(nc.loc[nc.cusip.isin(cc - pc), "ticker"])
        outs = sorted(prev.loc[prev.cusip.isin(pc - cc), "ticker"])
    row.update(names_in_count=None if ins is None else len(ins),
               names_out_count=None if outs is None else len(outs),
               names_in=None if ins is None else ",".join(ins),
               names_out=None if outs is None else ",".join(outs))
    return row


def build_portfolio_summary(holdings: pd.DataFrame) -> pd.DataFrame:
    qs = sorted(holdings.quarter.unique())
    rows, prev = [], None
    for qq in qs:
        cur = holdings[holdings.quarter == qq]
        rows.append(summarise_quarter(cur, prev))
        prev = cur
    df = pd.DataFrame(rows)
    for c in ("names_in_count", "names_out_count"):
        df[c] = df[c].astype("Int64")
    return df


def build_sector_weights(holdings: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    m = holdings.merge(ref[["cusip", "gics_sector"]], on="cusip", how="left", validate="m:1")
    out = (m.groupby(["quarter", "gics_sector"], as_index=False)
           .agg(weight_pct=("weight_pct", "sum"), n_positions=("cusip", "count")))
    return out.sort_values(["quarter", "weight_pct"], ascending=[True, False]).reset_index(drop=True)
