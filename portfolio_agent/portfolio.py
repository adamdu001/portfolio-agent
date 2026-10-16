"""Portfolio-level summary and sector weights."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .reference import CASH_SECTOR


@dataclass(frozen=True)
class SectorConfig:
    # Tunable default, not derived from data: a sector whose weight moves by at least this many
    # percentage points between two quarters is flagged as a tilt.
    min_shift_pp: float = 3.0


def _sector_view(q: pd.DataFrame, ref: pd.DataFrame) -> pd.DataFrame:
    """Sector weight_pct and position count for one quarter (cash excluded)."""
    m = q[~q.is_cash].merge(ref[["cusip", "gics_sector"]], on="cusip", how="left", validate="m:1")
    g = m.groupby("gics_sector")
    return pd.DataFrame({"weight_pct": g["weight_pct"].sum(), "n": g["cusip"].count()})


def summarise_quarter(q: pd.DataFrame, prev: pd.DataFrame | None,
                      ref: pd.DataFrame | None = None) -> dict:
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
    if ref is not None:
        sv = _sector_view(q, ref)
        sn = sv.weight_pct / sv.weight_pct.sum()          # weights ex cash, as for stock HHI
        shhi = float((sn ** 2).sum() * 10000)
        sin = sout = None
        if prev is not None:
            ps, cs = set(_sector_view(prev, ref).index), set(sv.index)
            sin, sout = sorted(cs - ps), sorted(ps - cs)
        row.update(n_sectors=len(sv), sector_hhi=shhi, top_sector=sv.weight_pct.idxmax(),
                   top_sector_weight=float(sv.weight_pct.max()),
                   sectors_in=None if sin is None else ",".join(sin),
                   sectors_out=None if sout is None else ",".join(sout))
    return row


def build_portfolio_summary(holdings: pd.DataFrame, ref: pd.DataFrame | None = None) -> pd.DataFrame:
    qs = sorted(holdings.quarter.unique())
    rows, prev = [], None
    for qq in qs:
        cur = holdings[holdings.quarter == qq]
        rows.append(summarise_quarter(cur, prev, ref))
        prev = cur
    df = pd.DataFrame(rows)
    for c in ("names_in_count", "names_out_count"):
        df[c] = df[c].astype("Int64")
    return df


def build_sector_weights(holdings: pd.DataFrame, ref: pd.DataFrame,
                         cfg: SectorConfig = SectorConfig()) -> pd.DataFrame:
    """Sector weight per quarter (cash is its own row), with the move since the previous quarter.

    `d_weight_pp` is the change in percentage points; a sector missing from a quarter counts as
    0%. `is_tilt` is true when |d_weight_pp| >= cfg.min_shift_pp; never true for cash.
    """
    m = holdings.merge(ref[["cusip", "gics_sector"]], on="cusip", how="left", validate="m:1")
    # groupby + reset_index (not as_index=False): older pandas drops keys with named agg
    g = m.groupby(["quarter", "gics_sector"])
    out = pd.DataFrame({"weight_pct": g["weight_pct"].sum(),
                        "n_positions": g["cusip"].count()}).reset_index()
    qs = sorted(out.quarter.unique())
    full = pd.MultiIndex.from_product([qs, sorted(out.gics_sector.unique())],
                                      names=["quarter", "gics_sector"])
    out = out.set_index(["quarter", "gics_sector"]).reindex(full).fillna(0).reset_index()
    out["n_positions"] = out.n_positions.astype(int)
    prev_w = out.assign(quarter=out.quarter.map(dict(zip(qs[:-1], qs[1:]))))
    prev_w = prev_w.dropna(subset=["quarter"]).set_index(["quarter", "gics_sector"]).weight_pct
    out["d_weight_pp"] = out.set_index(["quarter", "gics_sector"]).index.map(prev_w.to_dict().get)
    out["d_weight_pp"] = out.weight_pct - out.d_weight_pp.astype(float)
    out["is_tilt"] = (out.d_weight_pp.abs() >= cfg.min_shift_pp) & (out.gics_sector != CASH_SECTOR)
    out = out[(out.weight_pct > 0) | (out.d_weight_pp.fillna(0) != 0)]   # drop sectors never held
    return out.sort_values(["quarter", "weight_pct"], ascending=[True, False]).reset_index(drop=True)
