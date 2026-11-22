import numpy as np
import pandas as pd

from edge import oil_tanks as ot


def synthetic(tmp_path, signal=True, n=160, seed=0):
    """Fake scenes: 3 floating-roof tanks whose shadow grows when stocks fall, 2 fixed-roof tanks."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-03", periods=n, freq="7D")
    stocks = 40 + 10 * np.sin(np.arange(n) / 9)  # million bbl
    eia = pd.DataFrame({"date": dates.strftime("%Y-%m-%d"), "stocks_kbbl": (stocks * 1000).round()})
    sun_el = 50 + 20 * np.sin(np.arange(n) / 52 * 2 * np.pi)
    cot = 1 / np.tan(np.radians(sun_el))
    rows = {"scene": [f"S{i}" for i in range(n)], "date": dates.strftime("%Y%m%d"), "sun_el": sun_el}
    for k in range(3):
        fill = (0.9 - 0.01 * stocks) if signal else 0.5
        rows[f"t{k + 1}"] = 0.1 + 0.3 * cot * fill + rng.normal(0, 0.01, n)
    for k in range(3, 5):
        rows[f"t{k + 1}"] = 0.05 + 0.1 * cot + rng.normal(0, 0.01, n)
    sp, ep = tmp_path / "shadows.csv", tmp_path / "eia.csv"
    pd.DataFrame(rows).to_csv(sp, index=False)
    eia.to_csv(ep, index=False)
    return sp, ep


def test_ols_recovers_coefficients():
    x = np.arange(20.0)
    b, t = ot.ols(3 + 2 * x, np.column_stack([np.ones(20), x]))
    assert np.allclose(b, [3, 2])


def test_load_interpolates_eia_between_fridays(tmp_path):
    sp, ep = synthetic(tmp_path)
    s, eia = ot.load(sp, ep)
    assert s["stocks"].notna().all() and "cot" in s
    assert abs(eia.iloc[0] - 40.0) < 0.01


def test_picks_floating_roof_tanks_and_tracks_stocks(tmp_path):
    s, eia = ot.load(*synthetic(tmp_path))
    o, out = ot.analyse(s, eia, split="20220101")
    assert o["picked"] == 3  # only the tanks whose shadow depends on fill
    assert o["test_coef"] < 0 and o["test_t"] < -3
    assert o["test_level_corr"] > 0.9


def test_no_signal_gives_no_edge_verdict(tmp_path):
    s, eia = ot.load(*synthetic(tmp_path, signal=False))
    o, _ = ot.analyse(s, eia, split="20220101")
    assert ot.verdict(o).startswith("No edge")


def test_report_written(tmp_path):
    s, eia = ot.load(*synthetic(tmp_path))
    o, _ = ot.analyse(s, eia, split="20220101")
    p = ot.write_report(o, tmp_path / "r.md")
    assert "Verdict" in p.read_text()
