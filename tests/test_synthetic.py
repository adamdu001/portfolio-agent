import pandas as pd
import pytest

from portfolio_agent.build import build
from portfolio_agent.load import load_all, normalise_cusip, reconcile
from portfolio_agent.signals import MaterialityConfig, build_signals, classify


SYNTH_ALIASES = {"000000011": [], "000000022": [], "000000033": [], "000000044": []}


def test_normalise_cusip():
    assert normalise_cusip(13091103) == "013091103"
    assert normalise_cusip("13091103") == "013091103"
    assert normalise_cusip(13091103.0) == "013091103"
    assert normalise_cusip("cash") == "CASH"
    assert normalise_cusip(float("nan")) is None


@pytest.mark.parametrize("p,c,a", [(0, 5, "initiate"), (5, 0, "exit"), (5, 6, "add"),
                                   (5, 4, "trim"), (5, 5, "hold")])
def test_classify(p, c, a):
    assert classify(p, c) == a


def test_load(synthetic_raw):
    raw, _ = synthetic_raw
    h, fd = load_all(raw)
    assert list(h.quarter.unique()) == ["2025Q4", "2026Q1"]
    assert len(h) == 8 and h.is_cash.sum() == 2
    assert "Comments" not in set(h.ticker)
    assert h.groupby("quarter").weight_pct.sum().round(0).eq(100).all()
    assert set(fd.file_prev_cusip.dropna()) >= {"000000011", "000000022"}  # zeros restored
    assert reconcile(h, fd).query("check != 'd_weight' and check != 'prev_weight'").empty


def test_signals(synthetic_raw):
    raw, _ = synthetic_raw
    h, _ = load_all(raw)
    s = build_signals(h).set_index("ticker")
    assert s.loc["AAA", "action"] == "add" and s.loc["BBB", "action"] == "hold"
    assert s.loc["CCC", "action"] == "exit" and pd.isna(s.loc["CCC", "active_w"])
    assert s.loc["DDD", "action"] == "initiate"
    # unchanged book at new prices: AAA 1200, BBB 900, CCC 1000 (imputed), cash 1000 -> 4100
    assert s.loc["AAA", "w_unchanged"] == pytest.approx(1200 / 4100 * 100)
    # exits are blank, so continuing rows sum to 100 minus the exit (CCC 1000/4100)
    assert s.w_unchanged.sum() == pytest.approx(3100 / 4100 * 100)
    cont = s[s.action.isin(("add", "trim", "hold"))]
    assert (cont.active_w + cont.passive_w - cont.d_w).abs().max() < 1e-9
    assert s.loc["CCC", "is_material"] and not s.loc["USD", "is_material"]
    assert pd.isna(s.loc["DDD", "active_w"])  # initiate: blank split
    strict = build_signals(h, MaterialityConfig(d_shares_pct=1000, active_w=1000, always_material=())
                           ).set_index("ticker")
    assert not strict.is_material.any()


def test_build_end_to_end(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    t = build(raw, tmp_path / "out", sectors, aliases=SYNTH_ALIASES)
    ps = t["portfolio_summary"].set_index("quarter")
    assert ps.loc["2025Q4", "n_positions"] == 3
    assert ps.loc["2026Q1", "names_in"] == "DDD" and ps.loc["2026Q1", "names_out"] == "CCC"
    sw = t["sector_weights"]
    assert set(sw.gics_sector) <= {"Energy", "Financials", "Utilities", "Cash"}
    assert (tmp_path / "out" / "signals.csv").exists()


def test_missing_sector_fails(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    sectors.write_text("cusip,ticker,gics_sector\n000000011,AAA,Energy\n")
    with pytest.raises(ValueError, match="no sector"):
        build(raw, tmp_path / "out", sectors)
