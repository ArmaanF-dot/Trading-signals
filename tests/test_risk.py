import json

import numpy as np
import pandas as pd

import config
from edge import dashboard, risk, track


def test_series_stats_known_values():
    r = pd.Series([0.02, -0.01] * 24)
    s = risk.series_stats(r)
    assert s["n"] == 48
    assert abs(s["sharpe"] - 0.005 / r.std(ddof=1) * np.sqrt(12)) < 1e-12
    assert abs(s["maxdd"] - (-0.01)) < 1e-12
    flat = risk.series_stats(pd.Series([0.01]))
    assert np.isnan(flat["sharpe"]) and flat["n"] == 1


def test_drawdown_compounds_from_the_peak():
    s = risk.series_stats(pd.Series([0.10, -0.20, -0.10, 0.50]))
    assert abs(s["maxdd"] - (0.8 * 0.9 - 1)) < 1e-12


def test_cohort_series_fills_empty_months_with_cash():
    m = risk.cohort_series(["2024-01-05", "2024-01-20", "2024-03-02"], [0.04, 0.02, -0.01])
    assert list(m.index.astype(str)) == ["2024-01", "2024-02", "2024-03"]
    assert np.allclose(m.values, [0.03, 0.0, -0.01])
    assert risk.cohort_series([], []).empty


def test_daily_to_monthly_compounds():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-02-01"])
    m = risk.daily_to_monthly(pd.Series([0.1, 0.1, -0.05], index=idx))
    assert np.allclose(m.values, [0.21, -0.05])


def test_sizing_refuses_without_edge_or_history():
    assert risk.sizing({"sharpe": 0.8, "vol": 0.05, "n": 120, "maxdd": -0.1})["leverage"] == 0
    assert "below 1.0" in risk.sizing({"sharpe": 0.8, "vol": 0.05, "n": 120, "maxdd": -0.1})["text"]
    short = risk.sizing({"sharpe": 3.0, "vol": 0.05, "n": 12, "maxdd": -0.02})
    assert short["leverage"] == 0 and "too short" in short["text"]
    assert risk.sizing({"sharpe": float("nan"), "vol": 0.05, "n": 60, "maxdd": 0})["leverage"] == 0


def test_sizing_with_edge_is_capped_and_rounded_down():
    calm = risk.sizing({"sharpe": 1.5, "vol": 0.03, "n": 60, "maxdd": -0.05})
    assert calm["leverage"] == risk.LEVER_CAP                      # 10% / 3% = 3.3x, capped at 2x
    lively = risk.sizing({"sharpe": 1.2, "vol": 0.08, "n": 60, "maxdd": -0.1})
    assert lively["leverage"] == 1.25                              # 10% / 8% = 1.25x
    wild = risk.sizing({"sharpe": 1.1, "vol": 0.30, "n": 60, "maxdd": -0.4})
    assert wild["leverage"] == 0.25                                # 10% / 30% = 0.33x, rounded down
    assert "paper trade" in calm["text"]


def _study_files(R):
    months = pd.period_range("2010-01", periods=120, freq="M").astype(str)
    rng = np.random.default_rng(0)
    g = rng.normal(0.008, 0.04, 120)
    pd.DataFrame({"month": months, "formed": months, "gross": g, "bench_ew": g + rng.normal(0.001, 0.02, 120), "net_0.002": g - 0.0005,
                  "net_0.02": g - 0.004, "net_0.03": g - 0.006}).to_csv(R / "momentum_monthly.csv", index=False)
    (R / "momentum_backtest.md").write_text("# Momentum\n\nBody.\n")
    n = 400
    dates = pd.date_range("2023-01-01", periods=n, freq="3D").strftime("%Y-%m-%d")
    pd.DataFrame({"entry_date": dates, "have_prices": True, "net_20d": rng.normal(-0.01, 0.1, n),
                  "excess_20d": rng.normal(-0.02, 0.1, n)}).to_csv(R / "form4_backtest_clusters.csv", index=False)


def test_run_writes_summary_and_stamps_reports_idempotently(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MOMENTUM_SPLIT", "2015-01")
    _study_files(tmp_path)
    text = risk.run(tmp_path)
    assert "12-1 momentum" in text and "Form 4 cluster buys" in text and "no study earns leverage" in text
    d = json.loads((tmp_path / "risk_summary.json").read_text())
    mom = d["studies"][0]
    assert mom["period"].startswith("2015-01") and mom["months"] == 60 and mom["sizing"]["leverage"] == 0
    once = (tmp_path / "momentum_backtest.md").read_text()
    risk.run(tmp_path)
    twice = (tmp_path / "momentum_backtest.md").read_text()
    assert once == twice and once.count("## Risk and sizing") == 1 and once.startswith("# Momentum")


def test_track_record_adds_risk_section_and_shorts_fca_rises():
    n = config.MIN_TRACK_N + 20
    dates = pd.date_range("2025-01-01", periods=n, freq="10D").strftime("%Y-%m-%d")
    df = pd.DataFrame({"public_date": dates, "ret_20d": [0.04] * n, "bench_ret_20d": [0.01] * n}).astype(str)
    rec = track.record("Form 4 clusters", df, 0.01, "public_date", "long")
    assert rec["ready"] and rec["priced"] == n and rec["sizing"]["leverage"] == 0   # under 36 months
    assert "too short" in rec["sizing"]["text"]
    fca = pd.DataFrame({"date": dates, "delta_pp": ["0.6", "-0.6"] * (n // 2), "ret_20d": [-0.05] * n,
                        "bench_ret_20d": [0.0] * n}).astype(str)
    short = track.record("FCA short changes", fca, 0.01, "date", "short")
    assert short["signal"].endswith("shorted") and short["logged"] == n // 2
    assert short["priced"] < config.MIN_TRACK_N or short["net"]["sharpe"] > 0
    few = track.record("UK combo", df.head(3), 0.01, "public_date", "long")
    assert not few["ready"] and "too few" in few["sizing"]["text"]
    md = "\n".join(track.risk_lines([rec, few]))
    assert "## Risk-adjusted record" in md and "| Form 4 clusters |" in md and "UK combo" in md


def test_dashboard_merges_live_and_backtest_rows(tmp_path):
    (tmp_path / "t.json").write_text(json.dumps({"guidance": "G", "signals": [
        {"signal": "Form 4 clusters", "ready": False, "priced": 2, "sizing": {"leverage": 0.0, "text": "None"}}]}))
    (tmp_path / "s.json").write_text(json.dumps({"guidance": "G", "studies": [
        {"study": "Momentum", "period": "2013-02 to 2026-11", "net": {"sharpe": 0.83, "maxdd": -0.2},
         "edge": {"sharpe": -0.01, "maxdd": -0.21}, "sizing": {"leverage": 0.0, "text": "None"}}]}))
    r = dashboard.risk_record(tmp_path / "t.json", tmp_path / "s.json")
    assert r["guidance"] == "G" and [x["kind"] for x in r["rows"]] == ["live", "backtest"]
    assert r["rows"][1]["edge_sharpe"] == -0.01 and r["rows"][0]["sharpe"] is None
    assert dashboard.risk_record(tmp_path / "none.json", tmp_path / "none2.json") is None
