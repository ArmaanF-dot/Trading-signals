import json

import pandas as pd

import config
from edge import feed, track


def clusters():
    return pd.DataFrame([{"issuer_cik": "1", "window_start": "2026-11-10", "signal_date": "2026-11-18", "public_date": "2026-11-19",
                          "ticker": "ACME", "issuer": "Acme", "n_insiders": "2", "total_value": "150000", "insiders": "A (CEO); B (CFO)",
                          "market_cap": "400000000"},
                         {"issuer_cik": "2", "window_start": "2026-08-01", "signal_date": "2026-08-05", "public_date": "2026-08-06",
                          "ticker": "OLD", "issuer": "Old", "n_insiders": "2", "total_value": "150000", "insiders": "X; Y", "market_cap": ""}])


def events():
    return pd.DataFrame([{"date": "2026-11-17", "event": "increase", "issuer": "Foo", "isin": "GB1", "delta_pp": "0.3", "ticker": "FOO.L"},
                         {"date": "2026-11-19", "event": "new", "issuer": "Foo", "isin": "GB1", "delta_pp": "0.4", "ticker": "FOO.L"},
                         {"date": "2026-11-19", "event": "cover", "issuer": "Bar", "isin": "GB2", "delta_pp": "-0.8", "ticker": ""},
                         {"date": "2026-11-19", "event": "increase", "issuer": "Baz", "isin": "GB3", "delta_pp": "0.2", "ticker": "BAZ.L"}])


def snap():
    return pd.DataFrame([{"issuer": "Foo", "isin": "GB1", "net_short_pct": 1.4, "position_date": ""}])


def test_feed_contents_and_ordering():
    f = feed.build_feed("2026-11-21", clusters(), events(), snap(), pd.DataFrame())
    sig = {s["id"].split(":")[0] + ":" + s["symbol"]: s for s in f["signals"]}
    assert "form4:ACME" in sig and "form4:OLD" not in sig           # old cluster is outside the lookback
    assert sig["fca:FOO.L"]["stance"] == "avoid" and sig["fca:FOO.L"]["metrics"]["net_change_pp"] == 0.7
    assert sig["fca:"]["stance"] == "info"                          # short covering is information only
    assert not any(s["symbol"] == "BAZ.L" for s in f["signals"])   # 0.2pp is below the threshold
    assert [s["stance"] for s in f["signals"]] == ["avoid", "watch", "info"]
    assert all(s["evidence"] for s in f["signals"]) and "no standalone edge" in f["disclaimer"]
    md = feed.to_markdown(f)
    assert "## Avoid" in md and "FOO.L" in md


def test_combo_record_and_empty_feed():
    combos = pd.DataFrame([{"signal_date": "2026-11-18", "company": "Foo", "isin": "GB1", "ticker": "FOO.L", "n_directors": "2",
                            "director_value_gbp": "50000", "total_net_short_pct": "1.4"}])
    f = feed.build_feed("2026-11-21", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), combos)
    assert f["signals"][0]["signal"] == "uk_combo" and f["signals"][0]["stance"] == "watch"
    assert "No active signals" in feed.to_markdown(feed.build_feed("2026-11-21", pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()))


def test_run_writes_files(tmp_path, monkeypatch):
    for name in ("FORM4_CLUSTERS_CSV", "FCA_EVENTS_CSV", "COMBO_CSV"):
        monkeypatch.setattr(config, name, tmp_path / (name + ".csv"))
    monkeypatch.setattr(config, "FCA_SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(config, "SIGNALS_DIR", tmp_path / "sig")
    monkeypatch.setattr(config, "FEED_JSON", tmp_path / "sig" / "feed.json")
    monkeypatch.setattr(config, "FEED_MD", tmp_path / "sig" / "feed.md")
    clusters().to_csv(config.FORM4_CLUSTERS_CSV, index=False)
    f = feed.run("2026-11-21")
    assert json.loads(config.FEED_JSON.read_text())["signals"][0]["id"] == f["signals"][0]["id"] and config.FEED_MD.exists()


def test_track_record_small_and_large_samples():
    small = track.table("X", pd.DataFrame({"ret_20d": ["0.05", ""], "bench_ret_20d": ["0.01", ""]}), 0.01)
    assert "Too few" in "\n".join(small)
    n = config.MIN_TRACK_N + 10
    big = pd.DataFrame({"ret_20d": [0.04] * n, "bench_ret_20d": [0.01] * n}).astype(str)
    txt = "\n".join(track.table("X", big, 0.01))
    assert "3.0%" in txt and "mean net excess" in txt and "2.0%" in txt
    assert "No signals logged yet" in "\n".join(track.table("X", pd.DataFrame(), 0.01))
