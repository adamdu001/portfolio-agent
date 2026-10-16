"""Resolve a spoken company name to a CUSIP using the security reference's alias column."""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .aliases import normalise_name


def alias_index(reference: pd.DataFrame) -> dict:
    """normalised alias -> cusip, built from the reference's `aliases` column."""
    idx = {}
    for cusip, aliases in zip(reference.cusip, reference.aliases.fillna("")):
        for a in filter(None, aliases.split("|")):
            idx[a] = cusip
    return idx


def resolve_company(name: str, reference: pd.DataFrame) -> Optional[str]:
    """CUSIP for a spoken name, or None when no held security carries that name."""
    return alias_index(reference).get(normalise_name(name))
