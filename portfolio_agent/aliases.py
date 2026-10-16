"""Spoken-name variants per security, and name normalisation for matching.

ALIASES lists extra spoken variants (beyond the official name in the holdings file) for every
non-cash security, keyed by CUSIP. An empty list is fine; a missing key fails the build, so a
new security cannot enter the reference without someone looking at its names.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

# Words dropped on both sides of a comparison, so "Qualcomm Inc" == "Qualcomm".
SUFFIX_WORDS = {"inc", "incorporated", "corp", "corporation", "co", "company", "plc", "ltd",
                "limited", "sa", "the", "holdings", "hldgs"}

ALIASES: Dict[str, List[str]] = {
    "02376R102": ["american airlines"], "013091103": ["albertsons"], "00130H105": [],
    "038222105": [], "023135106": ["amazon"], "06849F108": ["barrick", "barrick gold"],
    "097023105": [], "060505104": ["bofa"], "055622104": ["british petroleum"],
    "084670702": ["berkshire"], "172967424": ["citi"],
    "M22465104": ["check point", "checkpoint"], "14040H105": ["capital one"],
    "79466L302": [], "126408103": [], "127097103": ["coterra"], "254687106": ["disney"],
    "036752103": ["elevance", "anthem"], "26884L109": [],
    "31620M106": ["fidelity national information services", "fis"], "Y2573F102": [],
    "36266G107": ["ge healthcare"], "37045V100": ["gm"], "02079K305": ["google"],
    "372460105": [], "446413106": ["huntington ingalls"], "G4705A100": [], "45337C102": [],
    "50155Q100": [], "49456B101": [], "844741108": ["southwest"], "G5960L103": [],
    "608190104": ["mohawk"], "573874104": ["marvell"], "636180101": ["national fuel"],
    "641069406": ["nestle"], "N6596X109": ["nxp semiconductors", "nxp"], "690742101": [],
    "681919106": ["omnicom"], "68389X105": [], "744573106": ["pseg"], "717081103": [],
    "747525103": [], "82846H405": [], "75886F107": ["regeneron"], "G8267P108": ["smurfit"],
    "G87052109": ["tyco electronics"], "881624209": ["teva"], "883556102": ["thermo fisher"],
    "911312106": ["ups"], "92840M102": [],
    "934423104": ["warner brothers discovery", "warner bros", "warner discovery"],
    "949746101": [], "G96629103": [], "98956P102": ["zimmer"],
}


def normalise_name(name: str) -> str:
    """Lowercase, strip accents and punctuation, drop corporate suffix words."""
    s = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", " ", s.lower().replace("&", " and "))
    return " ".join(w for w in s.split() if w not in SUFFIX_WORDS)


def aliases_for(cusip: str, ticker: str, name: str,
                extra: Optional[Dict[str, List[str]]]) -> List[str]:
    """Normalised, de-duplicated variants: official name, ticker (3+ letters), hand-written extras."""
    out = [normalise_name(name)]
    if len(ticker) >= 3:
        out.append(normalise_name(ticker))
    out += [normalise_name(a) for a in (extra or {}).get(cusip, [])]
    return list(dict.fromkeys(a for a in out if a))
