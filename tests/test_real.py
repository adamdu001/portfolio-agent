"""Assertions against the confidential files; skipped when data/raw/ is empty."""
import pytest

from conftest import RAW, real
from portfolio_agent.build import build
from portfolio_agent.reference import GICS_SECTORS

TOL = 0.02
pytestmark = real


@pytest.fixture(scope="module")
def t(tmp_path_factory):
    return build(RAW, tmp_path_factory.mktemp("out"))


def sig(t, ticker, fq):
    s = t["signals"]
    return s[(s.ticker == ticker) & (s.from_q == fq)].iloc[0]


def test_qcom_q4_q1(t):
    r = sig(t, "QCOM", "2025Q4")
    assert (r.shares_prev, r.shares_curr, r.action) == (16495, 12995, "trim")
    assert r.w_prev == pytest.approx(2.78, abs=TOL) and r.w_curr == pytest.approx(1.70, abs=TOL)
    assert r.w_unchanged == pytest.approx(2.13, abs=TOL)
    assert r.active_w == pytest.approx(-0.43, abs=TOL)
    assert r.passive_w == pytest.approx(-0.65, abs=TOL)


def test_qcom_q1_q2(t):
    r = sig(t, "QCOM", "2026Q1")
    assert r.action == "add"
    assert r.active_w == pytest.approx(0.62, abs=TOL)
    assert r.passive_w == pytest.approx(0.61, abs=TOL)


def test_actions(t):
    for tk in ("B", "WBD"):
        assert sig(t, tk, "2025Q4").action == "exit"
    assert sig(t, "BA", "2025Q4").action == "initiate"


def test_invariants(t):
    s = t["signals"]
    assert (s.active_w + s.passive_w - s.d_w).abs().max() < 1e-9
    assert s.groupby("from_q").w_unchanged.sum().sub(100).abs().max() < 1e-9
    h = t["holdings"]
    assert h.groupby("quarter").weight_pct.sum().sub(100).abs().max() < 0.05
    assert h.loc[~h.is_cash, "cusip"].str.len().eq(9).all()
    assert t["reconciliation"].empty


def test_summary(t):
    ps = t["portfolio_summary"].set_index("quarter")
    assert ps.loc["2025Q4", "n_positions"] == 37
    assert ps.loc["2025Q4", "hhi"] == pytest.approx(283, abs=0.5)
    assert ps.loc["2025Q4", "top10_weight_pct"] == pytest.approx(32.2, abs=TOL)
    assert ps.loc["2026Q1", "n_positions"] == 39


def test_reference_complete(t):
    ref = t["security_reference"]
    assert ref.gics_sector.notna().all()
    assert set(ref.gics_sector) <= GICS_SECTORS | {"Cash"}
    assert len(ref) == 56
