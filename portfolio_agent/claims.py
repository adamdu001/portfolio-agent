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


def locate_quote(quote: str, transcript: str) -> List[Dict]:
    """Every place the quote occurs (whitespace-insensitive): start/end character offsets and the
    1-based number of the paragraph (non-empty line) where it starts."""
    words = quote.split()
    if not words:
        return []
    pattern = re.compile(r"\s+".join(re.escape(w) for w in words))
    spans = [m.span() for m in pattern.finditer(transcript)]
    bounds, pos, k = [], 0, 0
    for line in transcript.splitlines(keepends=True):
        if line.strip():
            k += 1
            bounds.append((pos, pos + len(line), k))
        pos += len(line)
    def para_of(off):
        return next((k for a, b, k in bounds if a <= off < b), None)
    return [{"start": a, "end": b, "paragraph": para_of(a)} for a, b in spans]


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


LOCATION_COLUMNS = ["offsets", "paragraphs", "quote_multiple_occurrences"]


def build_claims_table(rows: List[Dict], transcript: str, source_id: str = "transcript"):
    """Validate model rows. Returns (valid claims DataFrame, rejected DataFrame with reasons).

    Code (not the model) adds source_id and the quote locations. `offsets` ("start-end") and
    `paragraphs` hold every match joined with ';' so each occurrence stays traceable;
    quote_multiple_occurrences is True when the quote appears more than once."""
    good, bad = [], []
    for row in rows:
        errs = validate_claim(row, transcript)
        (bad if errs else good).append({**row, "problems": "; ".join(errs)} if errs else dict(row))
    claims = pd.DataFrame(good, columns=COLUMNS[1:]).reset_index(drop=True)
    locs = [locate_quote(q, transcript) for q in claims.quote]
    claims["offsets"] = [";".join(f"{m['start']}-{m['end']}" for m in L) for L in locs]
    claims["paragraphs"] = [";".join(str(m["paragraph"]) for m in L) for L in locs]
    claims["quote_multiple_occurrences"] = [len(L) > 1 for L in locs]
    claims.insert(0, "claim_id", [f"C{i + 1}" for i in range(len(claims))])
    claims.insert(1, "source_id", source_id)
    return claims, pd.DataFrame(bad)
