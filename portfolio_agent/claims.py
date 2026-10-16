"""Claims table: schema, validation of model output against the transcript."""
from __future__ import annotations

import re
from typing import Dict, List

import pandas as pd

ACTIONS = ("initiate", "add", "hold", "trim", "exit")
QUARTER_BASIS = ("stated", "inferred_from_call_date")
COLUMNS = ["claim_id", "quote", "company", "action", "quarter", "quarter_basis",
           "multi_quarter", "duration_phrase", "rationale"]

# JSON schema handed to the model's structured-output setting.
JSON_SCHEMA = {
    "type": "object",
    "properties": {"claims": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "quote": {"type": "string"},
            "company": {"type": "string"},
            "action": {"type": "string", "enum": list(ACTIONS)},
            "quarter": {"type": "string", "pattern": r"^\d{4}Q[1-4]$"},
            "quarter_basis": {"type": "string", "enum": list(QUARTER_BASIS)},
            "multi_quarter": {"type": "boolean"},
            "duration_phrase": {"type": ["string", "null"]},
            "rationale": {"type": "string"},
        },
        "required": ["quote", "company", "action", "quarter", "quarter_basis",
                     "multi_quarter", "duration_phrase", "rationale"],
        "additionalProperties": False}}},
    "required": ["claims"], "additionalProperties": False,
}


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate_claim(row: Dict, transcript: str) -> List[str]:
    """Return a list of problems with one model-produced claim (empty list = valid)."""
    errs = []
    missing = [c for c in COLUMNS[1:] if c not in row]
    if missing:
        return [f"missing fields: {missing}"]
    if _squash(row["quote"]) not in _squash(transcript) or not row["quote"].strip():
        errs.append("quote is not a verbatim substring of the transcript")
    if not str(row["company"]).strip():
        errs.append("empty company")
    if row["action"] not in ACTIONS:
        errs.append(f"invalid action {row['action']!r}")
    if not re.fullmatch(r"\d{4}Q[1-4]", str(row["quarter"])):
        errs.append(f"invalid quarter {row['quarter']!r}")
    if row["quarter_basis"] not in QUARTER_BASIS:
        errs.append(f"invalid quarter_basis {row['quarter_basis']!r}")
    if not isinstance(row["multi_quarter"], bool):
        errs.append("multi_quarter must be true or false")
    elif row["multi_quarter"] and not row["duration_phrase"]:
        errs.append("multi_quarter is true but duration_phrase is empty")
    elif not row["multi_quarter"] and row["duration_phrase"]:
        errs.append("duration_phrase given but multi_quarter is false")
    return errs


def build_claims_table(rows: List[Dict], transcript: str):
    """Validate model rows. Returns (valid claims DataFrame, rejected DataFrame with reasons)."""
    good, bad = [], []
    for row in rows:
        errs = validate_claim(row, transcript)
        (bad if errs else good).append({**row, "problems": "; ".join(errs)} if errs else dict(row))
    claims = pd.DataFrame(good, columns=COLUMNS[1:]).reset_index(drop=True)
    claims.insert(0, "claim_id", [f"C{i + 1}" for i in range(len(claims))])
    return claims, pd.DataFrame(bad)
