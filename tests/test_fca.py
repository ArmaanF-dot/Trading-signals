import pandas as pd

from conftest import make_fca_xlsx
from edge.fca import shorts


def snap(rows):
    return pd.DataFrame(rows, columns=shorts.SNAP_COLS)


def test_parse_xlsx(tmp_path):
    p = tmp_path / "f.xlsx"
    make_fca_xlsx(p, [("Fund A", "Foo plc", "GB0001", "0.75", "2026-11-18"),
                      ("Fund B", "Bar plc", "GB0002", "1.2", "2026-11-17"),
                      ("Bad", "Baz", "", "x", "")])
    df = shorts.parse_xlsx(p)
    assert list(df.columns) == shorts.SNAP_COLS and len(df) == 2
    assert df.loc[0, "net_short_pct"] == 0.75 and df.loc[0, "position_date"] == "2026-11-18"


def test_diff_events():
    prev = snap([("A", "Foo", "GB1", 0.6, "d"), ("B", "Bar", "GB2", 1.0, "d"), ("C", "Baz", "GB3", 0.8, "d"),
                 ("D", "Qux", "GB4", 0.5, "d")])
    cur = snap([("A", "Foo", "GB1", 0.9, "d"), ("B", "Bar", "GB2", 1.0, "d"), ("C", "Baz", "GB3", 0.6, "d"),
                ("E", "New", "GB5", 0.5, "d")])
    ev = shorts.diff(prev, cur, "2026-11-20").set_index("holder")
    assert ev.loc["A", "event"] == "increase" and ev.loc["A", "delta_pp"] == 0.3
    assert ev.loc["C", "event"] == "decrease"
    assert ev.loc["D", "event"] == "cover" and ev.loc["E", "event"] == "new"
    assert "B" not in ev.index


def test_process_snapshots_and_events(tmp_path, monkeypatch, capsys):
    import config
    from edge.fca import run
    monkeypatch.setattr(config, "FCA_SNAPSHOT_DIR", tmp_path / "snaps")
    monkeypatch.setattr(config, "FCA_EVENTS_CSV", tmp_path / "events.csv")
    monkeypatch.setattr(config, "ISIN_TICKER_CSV", tmp_path / "none.csv")
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert run.process(snap([("A", "Foo", "GB1", 0.6, "d")]), "2026-11-19").empty
    new = run.process(snap([("B", "Bar", "GB2", 0.7, "d")]), "2026-11-20")
    assert set(new["event"]) == {"new", "cover"}
    assert "DRY RUN" in capsys.readouterr().out
    # re-running the same day does not duplicate events
    run.process(snap([("B", "Bar", "GB2", 0.7, "d")]), "2026-11-20")
    assert len(pd.read_csv(tmp_path / "events.csv")) == 2
