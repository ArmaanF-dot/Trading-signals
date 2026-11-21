import pandas as pd

from conftest import FIX
from edge.fca import shorts


def snap(rows):
    return pd.DataFrame(rows, columns=shorts.SNAP_COLS)


def test_parse_csv_fixture():
    df = shorts.parse_csv((FIX / "fca_ansp.csv").read_text())
    assert list(df.columns) == shorts.SNAP_COLS and len(df) == 2
    assert df.loc[0, "net_short_pct"] == 0.82 and df.loc[0, "position_date"] == "2026-10-19"


def test_diff_events():
    prev = snap([("Foo", "GB1", 0.6, "d"), ("Bar", "GB2", 1.0, "d"), ("Baz", "GB3", 0.8, "d"), ("Qux", "GB4", 0.5, "d")])
    cur = snap([("Foo", "GB1", 0.9, "d"), ("Bar", "GB2", 1.0, "d"), ("Baz", "GB3", 0.6, "d"), ("New", "GB5", 0.5, "d")])
    ev = shorts.diff(prev, cur, "2026-11-20").set_index("isin")
    assert ev.loc["GB1", "event"] == "increase" and ev.loc["GB1", "delta_pp"] == 0.3
    assert ev.loc["GB3", "event"] == "decrease"
    assert ev.loc["GB4", "event"] == "cover" and ev.loc["GB5", "event"] == "new"
    assert "GB2" not in ev.index


def test_process_snapshots_and_events(tmp_path, monkeypatch, capsys):
    import config
    from edge.fca import run
    monkeypatch.setattr(config, "FCA_SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(config, "FCA_EVENTS_CSV", tmp_path / "events.csv")
    monkeypatch.setattr(config, "ISIN_TICKER_CSV", tmp_path / "none.csv")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert run.process(snap([("Foo", "GB1", 0.6, "d")]), "2026-11-19").empty
    new = run.process(snap([("Bar", "GB2", 0.7, "d")]), "2026-11-20")
    assert set(new["event"]) == {"new", "cover"}
    assert "DRY RUN" in capsys.readouterr().out
    run.process(snap([("Bar", "GB2", 0.7, "d")]), "2026-11-20")  # same day again: no duplicates
    assert len(pd.read_csv(tmp_path / "events.csv")) == 2


def test_parse_csv_survives_bom_and_mojibake():
    text = (FIX / "fca_ansp.csv").read_text()
    assert len(shorts.parse_csv("\ufeff" + text)) == 2
    assert len(shorts.parse_csv("\u00ef\u00bb\u00bf" + text)) == 2  # BOM mis-decoded as latin-1


def test_download_decodes_bom(monkeypatch):
    class R:
        content = b"\xef\xbb\xbf" + (FIX / "fca_ansp.csv").read_bytes()
    monkeypatch.setattr(shorts.http, "get", lambda *a, **k: R())
    assert shorts.download().startswith("Name of Company")
