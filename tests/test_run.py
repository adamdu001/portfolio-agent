import pandas as pd
import pytest

from conftest import REAL_FILES, ROOT
from portfolio_agent.run import InputError, run_pipeline
from test_flags import ALIASES, TRANSCRIPT


def stub(_text):
    return [dict(quote="We bought more AAA.", company="AAA", action="add", quarter="2026Q1",
                 quarter_basis="stated", multi_quarter=False, duration_phrase=None, rationale="x"),
            dict(quote="never said this", company="BBB", action="trim", quarter="2026Q1",
                 quarter_basis="stated", multi_quarter=False, duration_phrase=None, rationale="x")]


def test_end_to_end(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    tr = tmp_path / "call.txt"
    tr.write_text(TRANSCRIPT)
    out = tmp_path / "out"
    s = run_pipeline(raw, tr, out, stub, sectors=sectors, aliases=ALIASES)
    assert s["claims_checked"] == 1 and s["claims_rejected"] == 1
    for f in ["signals.csv", "claim_checks.csv", "claims_rejected.csv", "flags.json", "report.md"]:
        assert (out / f).exists()
    assert pd.read_csv(out / "claim_checks.csv").source_id.tolist() == ["call"]
    assert "Portfolio evidence report" in (out / "report.md").read_text()


def test_skip_claims_removes_stale(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    out = tmp_path / "out"
    out.mkdir()
    (out / "claim_checks.csv").write_text("stale")
    s = run_pipeline(raw, tmp_path / "none.txt", out, skip_claims=True, sectors=sectors, aliases=ALIASES)
    assert "claims_checked" not in s and "No claim check was run" in (out / "report.md").read_text()


def test_missing_inputs(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    with pytest.raises(InputError, match="transcript not found"):
        run_pipeline(raw, tmp_path / "none.txt", tmp_path / "o", sectors=sectors, aliases=ALIASES)
    with pytest.raises(InputError, match="at least 2"):
        run_pipeline(tmp_path / "empty", tmp_path / "none.txt", tmp_path / "o", skip_claims=True)


@pytest.mark.skipif(len(REAL_FILES) < 3 or not (ROOT / "data/transcripts/q1_2026_call.txt").exists(),
                    reason="confidential files not present")
def test_real_end_to_end(tmp_path):
    s = run_pipeline(out_dir=tmp_path / "out")
    assert (s["claims_checked"], s["claim_inconsistencies"], s["stock_flags"], s["sector_flags"]) == (4, 2, 53, 7)
