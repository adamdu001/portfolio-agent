"""Render the flags structure as a Markdown report. Tables and sentences come from code only."""
from __future__ import annotations

from typing import Any, Dict, List


def _fmt(v, nd=2, signed=False):
    if v is None:
        return "–"
    return f"{v:+.{nd}f}" if signed else f"{v:,.{nd}f}"


def _stock_table(items: List[Dict[str, Any]]) -> List[str]:
    lines = ["| id | action | shares | weight % | trading pp | price pp | streak | rows (prev, curr) |",
             "|---|---|---|---|---|---|---|---|"]
    for r in items:
        lines.append(
            f"| {r['id']} | {r['action']} | {r['shares_prev']:,.0f} → {r['shares_curr']:,.0f} | "
            f"{_fmt(r['w_prev'])} → {_fmt(r['w_curr'])} | {_fmt(r['active_w'], signed=True)} | "
            f"{_fmt(r['passive_w'], signed=True)} | {r['streak']} | "
            f"{r['prev_source_row'] if r['prev_source_row'] is not None else '–'}, "
            f"{r['curr_source_row'] if r['curr_source_row'] is not None else '–'} |")
    return lines


def render_markdown(flags: Dict[str, Any]) -> str:
    L = ["# Portfolio evidence report", "",
         "Everything below is computed from the holdings files and the call transcript by fixed "
         "rules. Items are evidence for follow-up, not conclusions about the manager's reasons.", "",
         "## 1. Claims that do not match the holdings", ""]
    if flags["claims_checked"] is None:
        L.append("_No claim check was run._")
    elif not flags["claim_inconsistencies"]:
        L.append(f"All {flags['claims_checked']} checked claims are consistent with the holdings.")
    else:
        L.append(f"{len(flags['claim_inconsistencies'])} of {flags['claims_checked']} checked claims "
                 "are not consistent.")
        for c in flags["claim_inconsistencies"]:
            L += ["", f"**{c['id']} · {c['company']}** — verdict: `{c['verdict']}`", "",
                  f"> {c['quote']}", "", c["reason"]]
            if c["observed_action"]:
                L.append(f"Evidence: shares {c['shares_prev']:,.0f} → {c['shares_curr']:,.0f}, "
                         f"trading effect {_fmt(c['active_w'], signed=True)} pp, source rows "
                         f"{c['prev_source_row']} and {c['curr_source_row']}.")
    L += ["", "## 2. Stock-level flags (material changes)", ""]
    steps = sorted({(r["from_q"], r["to_q"]) for r in flags["stock_flags"]})
    for fq, tq in steps:
        items = [r for r in flags["stock_flags"] if (r["from_q"], r["to_q"]) == (fq, tq)]
        ins = [r["ticker"] for r in items if r["action"] == "initiate"]
        outs = [r["ticker"] for r in items if r["action"] == "exit"]
        L += [f"### {fq} to {tq}", "",
              f"{len(items)} material changes; {len(ins)} new positions and {len(outs)} exits.",
              f"New: {', '.join(ins) or 'none'}. Exited: {', '.join(outs) or 'none'}.", ""]
        L += _stock_table(items) + [""]
    L += ["## 3. Sector and portfolio flags", "", "### Sector tilts", ""]
    L += [f"- {s['summary']}" for s in flags["sector_flags"]] or ["_No sector moved past the threshold._"]
    L += ["", "### Concentration", "",
          "| quarter | stock HHI | sector HHI | change | top sector | top-10 stocks % |",
          "|---|---|---|---|---|---|"]
    for c in flags["concentration"]:
        L.append(f"| {c['quarter']} | {c['hhi']:.0f} | {c['sector_hhi']:.0f} | "
                 f"{_fmt(c['sector_hhi_change'], 0, True)} | {c['top_sector']} "
                 f"{c['top_sector_weight']:.1f}% | {c['top10_weight_pct']:.1f} |")
    L += ["", f"Sector HHI ranges from {flags['concentration'][0]['sector_hhi_floor']:.0f} "
          "(even spread over 11 sectors) to 10,000 (one sector)."]
    return "\n".join(L) + "\n"
