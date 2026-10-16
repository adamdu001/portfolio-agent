"""Claim extraction: the prompt, and a pluggable extractor (stub now, real model later).

An extractor is any function `transcript_text -> list of claim dicts` in the schema of claims.py.
"""
from __future__ import annotations

from typing import Callable, Dict, List

PROMPT = """You extract stock-specific portfolio actions from a fund manager's call transcript.

Context: this is the {call_label} call ({call_quarter}).

Extract one entry for each concrete action the manager says they took on a named stock.
An action is one of: initiate (new position), add (bought more), hold (kept, no change),
trim (reduced), exit (sold entirely).

Rules:
- One entry per stock and action. "Trimmed A and added B" gives two entries.
- Only include actions the manager states. Never infer an action from opinions or sentiment.
- Ignore statements about no particular stock, such as general views on risk or the market.
- "company" is the company name as spoken. Do not output tickers or identifiers.
- "quote" must be copied exactly from the transcript.
- "rationale" summarises the manager's reasons for that stock in one sentence, using only what
  they said. Follow-on sentences that clearly refer back to the stock count as its reasons.
- "quarter" is the quarter the action happened in. If the manager states a time within this
  quarter ("in January"), use that quarter and set quarter_basis to "stated". Otherwise use
  {call_quarter} and set quarter_basis to "inferred_from_call_date".
- Set multi_quarter to true only if the manager says the action has been happening over
  several quarters ("for a few quarters now"). Otherwise false. If true, copy the exact
  words into duration_phrase; if false, set it to null.
- If there are no such actions, return an empty list.

Transcript:
{transcript}
"""

Extractor = Callable[[str], List[Dict]]


def render_prompt(transcript: str, call_label: str = "Q1 2026", call_quarter: str = "2026Q1") -> str:
    return PROMPT.format(call_label=call_label, call_quarter=call_quarter, transcript=transcript)


# What we expect a good model to return for the case-study excerpt. Used as a stand-in so the
# code after extraction can be built and tested before a real model is plugged in.
STUB_ROWS: List[Dict] = [
    {"quote": "We've been reducing Kraft Heinz for a few quarters now.", "company": "Kraft Heinz",
     "action": "trim", "quarter": "2026Q1", "quarter_basis": "inferred_from_call_date",
     "multi_quarter": True, "duration_phrase": "for a few quarters now",
     "rationale": "Less convinced about the pace of recovery; no longer top conviction, though still a holder."},
    {"quote": "we added Qualcomm in January.", "company": "Qualcomm", "action": "add",
     "quarter": "2026Q1", "quarter_basis": "stated", "multi_quarter": False, "duration_phrase": None,
     "rationale": "Believes the AI-on-device cycle is underestimated and QCOM is a clear beneficiary, with royalties as a cushion."},
    {"quote": "We also initiated a position in Boeing.", "company": "Boeing", "action": "initiate",
     "quarter": "2026Q1", "quarter_basis": "inferred_from_call_date", "multi_quarter": False,
     "duration_phrase": None,
     "rationale": "Long-horizon recovery play; franchise value intact and the stock prices in a worst case."},
    {"quote": "We exited Warner Bros. Discovery entirely.", "company": "Warner Bros. Discovery",
     "action": "exit", "quarter": "2026Q1", "quarter_basis": "inferred_from_call_date",
     "multi_quarter": False, "duration_phrase": None,
     "rationale": "Streaming content spend higher than modelled and the balance sheet leaves little room."},
]


def stub_extractor(transcript: str) -> List[Dict]:
    return [dict(r) for r in STUB_ROWS]
