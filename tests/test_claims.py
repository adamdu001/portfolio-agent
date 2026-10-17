import copy

import pandas as pd
import pytest

from conftest import REAL_FILES, RAW, ROOT
from portfolio_agent.aliases import ALIASES, normalise_name
from portfolio_agent.build import build
from portfolio_agent.claims import build_claims_table, locate_quote, validate_claim
from portfolio_agent.extract import STUB_ROWS, render_prompt, stub_extractor
from portfolio_agent.matching import resolve_company
from portfolio_agent.reference import build_security_reference
from portfolio_agent.verdicts import ClaimCheckConfig, check_claims

SYNTH_ALIASES = {"000000011": [], "000000022": [], "000000033": [], "000000044": ["delta"]}
TRANSCRIPT = ("We bought more AAA. We trimmed BBB. We initiated DDD, or Delta as we call it. "
              "We have been exiting CCC for a few quarters. We looked at Zeta Corp too.")


def claim(company, action, quote, quarter="2026Q1", multi=False, phrase=None):
    return {"quote": quote, "company": company, "action": action, "quarter": quarter,
            "quarter_basis": "stated", "multi_quarter": multi, "duration_phrase": phrase,
            "rationale": "because"}


@pytest.fixture
def tables(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    return build(raw, tmp_path / "out", sectors, aliases=SYNTH_ALIASES)


def test_normalise_name():
    assert normalise_name("Warner Bros. Discovery") == normalise_name("Warner Bros Discovery Inc")
    assert normalise_name("Walt Disney Company (the)") == "walt disney"
    assert normalise_name("Nestlé SA") == "nestle"


def test_real_alias_table_has_no_collisions_and_covers_names():
    assert len(ALIASES) == 55
    assert normalise_name("Qualcomm") != normalise_name("Warner Bros")


def test_reference_requires_alias_entry_and_unique_aliases(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    from portfolio_agent.load import load_all
    from portfolio_agent.reference import load_sectors
    h, _ = load_all(raw)
    sec = load_sectors(sectors)
    with pytest.raises(ValueError, match="no aliases entry"):
        build_security_reference(h, sec, {"000000011": []})
    clash = dict(SYNTH_ALIASES, **{"000000022": ["aaa"]})
    with pytest.raises(ValueError, match="belongs to two securities"):
        build_security_reference(h, sec, clash)


def test_resolve_company(tables):
    ref = tables["security_reference"]
    assert resolve_company("AAA Inc", ref) == "000000011"
    assert resolve_company("Delta", ref) == "000000044"
    assert resolve_company("Zeta Corp", ref) is None


def test_validation():
    ok = claim("AAA", "add", "We bought more AAA.")
    assert validate_claim(ok, TRANSCRIPT) == []
    assert validate_claim(dict(ok, quote="never said"), TRANSCRIPT)
    assert validate_claim(dict(ok, action="buy"), TRANSCRIPT)
    assert validate_claim(dict(ok, quarter="Q1 2026"), TRANSCRIPT)
    assert validate_claim(dict(ok, multi_quarter=True), TRANSCRIPT)       # no duration phrase
    assert validate_claim(dict(ok, duration_phrase="for years"), TRANSCRIPT)  # flag is false
    claims, rejected = build_claims_table([ok, dict(ok, action="buy")], TRANSCRIPT)
    assert len(claims) == 1 and claims.claim_id.tolist() == ["C1"] and len(rejected) == 1


def test_verdicts(tables):
    rows = [claim("AAA", "add", "We bought more AAA."),
            claim("BBB", "trim", "We trimmed BBB."),
            claim("Delta", "initiate", "We initiated DDD, or Delta as we call it."),
            claim("CCC", "exit", "We have been exiting CCC for a few quarters.",
                  multi=True, phrase="for a few quarters"),
            claim("Zeta Corp", "add", "We looked at Zeta Corp too."),
            claim("AAA", "add", "We bought more AAA.", quarter="2026Q3")]
    claims, rejected = build_claims_table(rows, TRANSCRIPT)
    assert rejected.empty
    out = check_claims(claims, tables["security_reference"], tables["signals"]).set_index("claim_id")
    assert out.verdict.tolist() == ["consistent", "contradicted", "consistent",
                                    "partially_supported", "not_in_holdings", "contradicted"]
    assert out.loc["C2", "observed_action"] == "hold"
    assert out.loc["C1", "curr_source_row"] is not None
    # lowering the streak rule makes the multi-quarter claim consistent
    easy = check_claims(claims, tables["security_reference"], tables["signals"],
                        ClaimCheckConfig(min_streak=1)).set_index("claim_id")
    assert easy.loc["C4", "verdict"] == "consistent"


def test_stub_and_prompt():
    rows = stub_extractor("")
    assert rows == STUB_ROWS and rows is not STUB_ROWS
    p = render_prompt("hello transcript")
    assert "hello transcript" in p and "2026Q1" in p and "{" not in p.replace("{}", "")


TRANSCRIPT_FILE = ROOT / "data" / "transcripts" / "q1_2026_call.txt"


@pytest.mark.skipif(len(REAL_FILES) < 3 or not TRANSCRIPT_FILE.exists(),
                    reason="confidential real files or transcript not present")
def test_real_case_study_claims(tmp_path):
    t = build(RAW, tmp_path / "out")
    text = TRANSCRIPT_FILE.read_text()
    claims, rejected = build_claims_table(stub_extractor(text), text)
    assert rejected.empty                      # every stub quote is verbatim in the transcript
    out = check_claims(claims, t["security_reference"], t["signals"]).set_index("company")
    assert out.loc["Kraft Heinz", "verdict"] == "not_in_holdings"
    assert out.loc["Qualcomm", "verdict"] == "contradicted"      # holdings show a trim into 2026Q1
    assert out.loc["Boeing", "verdict"] == "consistent"
    assert out.loc["Warner Bros. Discovery", "verdict"] == "consistent"


def test_quote_locations():
    text = "First para.\n\nWe bought more AAA.\nWe trimmed BBB. Then\nwe trimmed BBB again.\nWe bought more AAA."
    one = locate_quote("We trimmed BBB.", text)
    assert [(m["start"], m["end"], m["paragraph"]) for m in one] == [(text.index("We trimmed"), text.index("We trimmed") + 15, 3)]
    two = locate_quote("We bought more AAA.", text)
    assert len(two) == 2 and [m["paragraph"] for m in two] == [2, 5]
    assert all(text[m["start"]:m["end"]] == "We bought more AAA." for m in two)
    assert locate_quote("never said", text) == []
    rows = [claim("AAA", "add", "We bought more AAA."), claim("BBB", "trim", "We trimmed BBB.")]
    claims, rej = build_claims_table(rows, text, "call_x")
    assert rej.empty and claims.source_id.tolist() == ["call_x", "call_x"]
    assert claims.quote_multiple_occurrences.tolist() == [True, False]
    assert claims.paragraphs.tolist() == ["2;5", "3"]
    assert claims.offsets[0].count(";") == 1 and ";" not in claims.offsets[1]
