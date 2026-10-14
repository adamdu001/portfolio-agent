"""Parse the quarterly holdings spreadsheets into a clean long table."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

HEADER_KEY = "Current Period"
FOOTER_KEYS = {"comments", "end of data"}
COLS = {
    "Identifier": "cusip", "Ticker": "ticker", "Name": "name",
    "Security Type": "security_type", "Shares": "shares", "Price": "price",
    "Weight": "weight_pct", "Country": "country",
}
FILE_DELTA_COLS = {"∆ Shares": "file_d_shares", "∆ Weight": "file_d_weight",
                   "Previous Identifier": "file_prev_cusip",
                   "Previous Shares": "file_prev_shares", "Previous Weight": "file_prev_weight"}


def normalise_cusip(x) -> str | None:
    """CUSIPs as 9-char strings; restores leading zeros lost to numeric coercion."""
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, float) and x.is_integer():
        x = int(x)
    s = str(x).strip().upper()
    if not s or s == "NAN":
        return None
    if s == "CASH":
        return s
    return s.zfill(9)


def quarter_label(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def load_holdings_file(path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (holdings, file_deltas). Holdings uses file values only."""
    path = Path(path)
    raw = pd.read_excel(path, header=None, dtype=object)
    first = raw.iloc[:, 0]
    hdr = [i for i, v in first.items() if isinstance(v, str) and v.strip() == HEADER_KEY]
    if not hdr:
        raise ValueError(f"{path.name}: header row '{HEADER_KEY}' not found")
    hdr = hdr[0]
    as_of = None
    for v in first.iloc[:hdr]:
        ts = v if isinstance(v, (dt.datetime, pd.Timestamp)) else None
        if ts is None and isinstance(v, str):
            ts = pd.to_datetime(v, errors="coerce")
            ts = None if pd.isna(ts) else ts
        if ts is not None:
            as_of = pd.Timestamp(ts).date()
            break
    if as_of is None:
        raise ValueError(f"{path.name}: as-of date not found above header")

    header = [str(c).strip() for c in raw.iloc[hdr]]
    body = raw.iloc[hdr + 1:].copy()
    body.columns = header
    body["source_row"] = body.index + 1  # 1-based Excel row number
    rows = []
    for _, r in body.iterrows():
        lead = r.iloc[0]
        if isinstance(lead, str) and lead.strip().lower() in FOOTER_KEYS:
            break
        if pd.isna(r.get("Identifier")) or pd.isna(r.get("Ticker")):
            continue
        rows.append(r)
    df = pd.DataFrame(rows)
    out = df[list(COLS) + ["source_row"]].rename(columns=COLS)
    out["cusip"] = out["cusip"].map(normalise_cusip)
    for c in ("shares", "price", "weight_pct"):
        out[c] = pd.to_numeric(out[c]).astype(float)
    for c in ("ticker", "name", "security_type", "country"):
        out[c] = out[c].astype(str).str.strip()
    out["is_cash"] = (out["cusip"] == "CASH") | (out["security_type"].str.lower() == "cash")
    out.insert(0, "as_of_date", as_of)
    out.insert(0, "quarter", quarter_label(as_of))
    out["source_file"] = path.name
    if out["cusip"].duplicated().any():
        raise ValueError(f"{path.name}: duplicate CUSIPs {out.loc[out.cusip.duplicated(), 'cusip'].tolist()}")
    out = out[["quarter", "as_of_date", "cusip", "ticker", "name", "security_type", "shares",
               "price", "weight_pct", "country", "is_cash", "source_file", "source_row"]]

    fd = df[[c for c in FILE_DELTA_COLS if c in df]].rename(columns=FILE_DELTA_COLS)
    fd.insert(0, "cusip", out["cusip"].values)
    fd.insert(0, "quarter", out["quarter"].values)
    if "file_prev_cusip" in fd:
        fd["file_prev_cusip"] = fd["file_prev_cusip"].map(normalise_cusip)
    for c in ("file_d_shares", "file_d_weight", "file_prev_shares", "file_prev_weight"):
        if c in fd:
            fd[c] = pd.to_numeric(fd[c], errors="coerce")
    return out.reset_index(drop=True), fd.reset_index(drop=True)


def load_all(raw_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    files = sorted(Path(raw_dir).glob("*.xlsx"))
    files = [f for f in files if not f.name.startswith("~$")]
    if not files:
        raise FileNotFoundError(f"no .xlsx files in {raw_dir}")
    parts = [load_holdings_file(f) for f in files]
    h = pd.concat([p[0] for p in parts], ignore_index=True)
    fd = pd.concat([p[1] for p in parts], ignore_index=True)
    if h.groupby("quarter")["source_file"].nunique().max() > 1:
        raise ValueError("two files map to the same quarter")
    return h.sort_values(["quarter", "cusip"]).reset_index(drop=True), fd


def reconcile(holdings: pd.DataFrame, file_deltas: pd.DataFrame, tol_shares=0.5, tol_w=0.015) -> pd.DataFrame:
    """Compare file's ∆/Previous columns with values recomputed from consecutive files.
    Reported only; never used downstream."""
    qs = sorted(holdings["quarter"].unique())
    out = []
    for prev_q, cur_q in zip(qs, qs[1:]):
        p = holdings[holdings.quarter == prev_q].set_index("cusip")
        c = holdings[holdings.quarter == cur_q].set_index("cusip")
        f = file_deltas[file_deltas.quarter == cur_q].set_index("cusip")
        for cusip, r in c.iterrows():
            ps = p["shares"].get(cusip, 0.0)
            pw = p["weight_pct"].get(cusip, 0.0)
            checks = {
                "d_shares": (r.shares - ps, f.at[cusip, "file_d_shares"]),
                "prev_shares": (ps, f.at[cusip, "file_prev_shares"] if pd.notna(f.at[cusip, "file_prev_shares"]) else 0.0),
                "d_weight": (r.weight_pct - pw, f.at[cusip, "file_d_weight"]),
                "prev_weight": (pw, f.at[cusip, "file_prev_weight"]),
            }
            fpc = f.at[cusip, "file_prev_cusip"]
            if cusip in p.index and fpc != cusip:
                out.append(dict(quarter=cur_q, cusip=cusip, ticker=r.ticker, check="prev_cusip",
                                computed=cusip, file=fpc, diff=None))
            for name, (comp, fil) in checks.items():
                tol = tol_shares if "shares" in name else tol_w
                if pd.isna(fil) or abs(comp - fil) > tol:
                    out.append(dict(quarter=cur_q, cusip=cusip, ticker=r.ticker, check=name,
                                    computed=comp, file=fil, diff=None if pd.isna(fil) else comp - fil))
    return pd.DataFrame(out, columns=["quarter", "cusip", "ticker", "check", "computed", "file", "diff"])
