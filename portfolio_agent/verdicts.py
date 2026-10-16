"""Rule-based comparison of each claim against the signals table. No language model here."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .matching import resolve_company

VERDICTS = ("consistent", "partially_supported", "contradicted", "not_in_holdings")
EVIDENCE = ["from_q", "to_q", "shares_prev", "shares_curr", "d_shares_pct", "active_w",
            "is_material", "streak", "prev_source_row", "curr_source_row"]


@dataclass(frozen=True)
class ClaimCheckConfig:
    # "A few quarters" is turned into a fixed rule: the stock must have moved the same way for
    # at least this many consecutive quarter steps. A tunable default, not derived from data.
    min_streak: int = 2


def check_claim(claim: pd.Series, reference: pd.DataFrame, signals: pd.DataFrame,
                cfg: ClaimCheckConfig) -> dict:
    out = {"cusip": None, "ticker": None, "observed_action": None, "verdict": None,
           "reason": None, **{c: None for c in EVIDENCE}}
    cusip = resolve_company(claim.company, reference)
    if cusip is None:
        out.update(verdict="not_in_holdings", reason=(
            f"'{claim.company}' matches no security held in any quarter (checked name variants)."))
        return out
    out["cusip"] = cusip
    out["ticker"] = reference.loc[reference.cusip == cusip, "ticker"].iloc[0]
    rows = signals[(signals.cusip == cusip) & (signals.to_q == claim.quarter)]
    if rows.empty:
        out.update(verdict="contradicted", reason=(
            f"{out['ticker']} was not held at either end of the step into {claim.quarter}."))
        return out
    r = rows.iloc[0]
    out.update({c: r[c] for c in EVIDENCE})
    out["observed_action"] = r.action
    if r.action != claim.action:
        out.update(verdict="contradicted", reason=(
            f"Manager says {claim.action}; holdings show {r.action} ({r.from_q} to {r.to_q})."))
    elif claim.multi_quarter and r.streak < cfg.min_streak:
        out.update(verdict="partially_supported", reason=(
            f"Direction matches ({r.action}), but the streak is {int(r.streak)} step(s), below the "
            f"{cfg.min_streak} needed for '{claim.duration_phrase}'. The data may be too short "
            f"to show longer streaks."))
    else:
        out.update(verdict="consistent", reason=(
            f"Holdings show {r.action} from {r.from_q} to {r.to_q}."
            + (f" Streak {int(r.streak)} step(s) supports '{claim.duration_phrase}'."
               if claim.multi_quarter else "")))
    return out


def check_claims(claims: pd.DataFrame, reference: pd.DataFrame, signals: pd.DataFrame,
                 cfg: ClaimCheckConfig = ClaimCheckConfig()) -> pd.DataFrame:
    res = pd.DataFrame([check_claim(row, reference, signals, cfg) for _, row in claims.iterrows()],
                       index=claims.index)
    return pd.concat([claims, res], axis=1)
