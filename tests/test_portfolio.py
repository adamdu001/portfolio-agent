import pandas as pd
import pytest

from conftest import RAW, real
from portfolio_agent.build import build
from portfolio_agent.portfolio import SectorConfig, build_sector_weights

ALIASES = {"000000011": [], "000000022": [], "000000033": [], "000000044": []}


@pytest.fixture
def t(synthetic_raw, tmp_path):
    raw, sectors = synthetic_raw
    return build(raw, tmp_path / "out", sectors, aliases=ALIASES)


def test_sector_summary(t):
    ps = t["portfolio_summary"].set_index("quarter")
    # Q4: Energy, Financials, Utilities equal -> three equal sectors ex cash: HHI 3333.3
    assert ps.loc["2025Q4", "sector_hhi"] == pytest.approx(10000 / 3, abs=1)
    assert ps.loc["2025Q4", "n_sectors"] == 3
    # Q1: Energy 2300, Financials 900 -> shares 0.71875 / 0.28125
    assert ps.loc["2026Q1", "sector_hhi"] == pytest.approx((0.71875 ** 2 + 0.28125 ** 2) * 10000, abs=1)  # weights are rounded to 2 dp
    assert ps.loc["2026Q1", "top_sector"] == "Energy"
    assert ps.loc["2026Q1", "sectors_out"] == "Utilities"
    assert ps.loc["2026Q1", "sectors_in"] == ""
    assert pd.isna(ps.loc["2025Q4", "sectors_in"])  # first quarter: nothing to compare with


def test_sector_changes_and_tilts(t):
    sw = t["sector_weights"].set_index(["quarter", "gics_sector"])
    assert sw.loc[("2026Q1", "Energy"), "d_weight_pp"] == pytest.approx(2300 / 3700 * 100 - 25, abs=0.05)
    assert sw.loc[("2026Q1", "Utilities"), "weight_pct"] == 0   # exited sector stays visible
    assert sw.loc[("2026Q1", "Utilities"), "d_weight_pp"] == pytest.approx(-25, abs=0.05)
    assert sw.loc[("2026Q1", "Energy"), "is_tilt"] and sw.loc[("2026Q1", "Utilities"), "is_tilt"]
    assert not sw.loc[("2026Q1", "Financials"), "is_tilt"]
    assert not sw.loc[("2026Q1", "Cash"), "is_tilt"]            # cash never a tilt
    assert sw.loc[("2025Q4", "Energy"), "d_weight_pp"] != sw.loc[("2025Q4", "Energy"), "d_weight_pp"]
    strict = build_sector_weights(t["holdings"], t["security_reference"], SectorConfig(min_shift_pp=99))
    assert not strict.is_tilt.any()


@real
def test_real_sector_tilts(tmp_path):
    t = build(RAW, tmp_path / "out")
    sw = t["sector_weights"].set_index(["quarter", "gics_sector"])
    assert sw.loc[("2026Q1", "Health Care"), "d_weight_pp"] == pytest.approx(6.98, abs=0.05)
    assert sw.loc[("2026Q1", "Financials"), "d_weight_pp"] == pytest.approx(-7.37, abs=0.05)
    assert sw.loc[("2026Q1", "Financials"), "is_tilt"]
    ps = t["portfolio_summary"]
    assert (ps.sector_hhi > 10000 / 11).all() and (ps.sector_hhi <= 10000).all()
