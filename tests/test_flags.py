import re
import json

import pandas as pd
import pytest

from conftest import RAW, real, ROOT
from portfolio_agent.build import build
from portfolio_agent.claims import build_claims_table
from portfolio_agent.extract import stub_extractor
from portfolio_agent.flags import build_flags
from portfolio_agent.render import render_markdown
from portfolio_agent.verdicts import check_claims

ALIASES = {"000000011": [], "000000022": [], "000000033": [], "000000044": []}
TRANSCRIPT = "We bought more AAA. We trimmed BBB. We initiated DDD. We exited Zeta Corp."


def claim(company, action, quote):
    return {"quote": quote, "company": company, "action": action, "quarter": "2026Q1",
            "quarter_basis": "stated", "multi_quarter": False, "duration_phrase": None,
            "rationale": "x"}


@pytest.fixture
def flags(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    t = build(raw, tmp_path / "out", sectors, aliases=ALIASES)
    claims, rej = build_claims_table(
        [claim("AAA", "add", "We bought more AAA."), claim("BBB", "trim", "We trimmed BBB."),
         claim("DDD", "initiate", "We initiated DDD."), claim("Zeta Corp", "exit", "We exited Zeta Corp.")],
        TRANSCRIPT)
    cc = check_claims(claims, t["security_reference"], t["signals"])
    return build_flags(t["signals"], t["sector_weights"], t["portfolio_summary"], cc), t


def test_claim_section_only_non_consistent(flags):
    f, _ = flags
    assert f["claims_checked"] == 4
    assert [c["id"] for c in f["claim_inconsistencies"]] == ["CL-C2", "CL-C4"]
    assert {c["verdict"] for c in f["claim_inconsistencies"]} == {"contradicted", "not_in_holdings"}
    assert f["claim_inconsistencies"][0]["observed_action"] == "hold"


def test_stock_flags_follow_is_material(flags):
    f, t = flags
    s = t["signals"]
    expected = s[s.is_material & ~s.is_cash]
    assert sorted(x["ticker"] for x in f["stock_flags"]) == sorted(expected.ticker)
    # initiates and exits come before add/trim/hold within a step
    acts = [x["action"] for x in f["stock_flags"]]
    first_continuing = next((i for i, a in enumerate(acts) if a not in ("initiate", "exit")), len(acts))
    assert all(a in ("initiate", "exit") for a in acts[:first_continuing])
    ddd = next(x for x in f["stock_flags"] if x["ticker"] == "DDD")
    assert ddd["id"] == "ST-DDD-2026Q1" and ddd["active_w"] is None and "initiated" in ddd["summary"]
    assert isinstance(ddd["curr_source_row"], int) and ddd["prev_source_row"] is None


def test_sector_and_concentration(flags):
    f, _ = flags
    assert {x["gics_sector"] for x in f["sector_flags"]} == {"Energy", "Utilities"}
    en = next(x for x in f["sector_flags"] if x["gics_sector"] == "Energy")
    assert en["weight_prev_pct"] == pytest.approx(25, abs=0.05) and "rose" in en["summary"]
    assert [c["quarter"] for c in f["concentration"]] == ["2025Q4", "2026Q1"]
    assert f["concentration"][0]["sector_hhi_change"] is None
    assert f["concentration"][1]["sector_hhi_change"] > 0
    assert f["concentration"][0]["sector_hhi_floor"] == pytest.approx(909.1)


def test_json_and_markdown(flags):
    f, _ = flags
    json.dumps(f)                                    # NaN and numpy types all converted
    md = render_markdown(f)
    assert "## 1. Claims that do not match the holdings" in md
    assert "CL-C2" in md and "ST-DDD-2026Q1" in md and "Sector tilts" in md
    assert not re.search(r"\bnan\b", md.lower())


def test_no_claim_check_run(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    t = build(raw, tmp_path / "out", sectors, aliases=ALIASES)
    f = build_flags(t["signals"], t["sector_weights"], t["portfolio_summary"], None)
    assert f["claim_inconsistencies"] == [] and f["claims_checked"] is None
    assert "No claim check was run" in render_markdown(f)


TRANSCRIPT_FILE = ROOT / "data" / "transcripts" / "q1_2026_call.txt"


@pytest.mark.skipif(len(__import__("conftest").REAL_FILES) < 3 or not TRANSCRIPT_FILE.exists(),
                    reason="confidential files not present")
def test_real_flags(tmp_path):
    t = build(RAW, tmp_path / "out")
    text = TRANSCRIPT_FILE.read_text()
    claims, _ = build_claims_table(stub_extractor(text), text)
    f = build_flags(t["signals"], t["sector_weights"], t["portfolio_summary"],
                    check_claims(claims, t["security_reference"], t["signals"]))
    assert [c["id"] for c in f["claim_inconsistencies"]] == ["CL-C1", "CL-C2"]
    assert len(f["stock_flags"]) == int((t["signals"].is_material & ~t["signals"].is_cash).sum()) == 53
    assert any(x["id"] == "ST-BA-2026Q1" and x["action"] == "initiate" for x in f["stock_flags"])
    assert {"Health Care", "Financials"} <= {x["gics_sector"] for x in f["sector_flags"]}
    assert not re.search(r"\bnan\b", render_markdown(f).lower())
