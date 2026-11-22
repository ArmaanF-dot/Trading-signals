import json
from datetime import date

import pandas as pd

from edge import dashboard as d


class Resp:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def json(self):
        return self.payload


def chart(price, closes, ts=1763740800):
    return {"chart": {"result": [{"meta": {"regularMarketPrice": price, "chartPreviousClose": closes[0],
                                           "currency": "GBp", "regularMarketTime": ts},
                                  "indicators": {"quote": [{"close": closes}]}}]}}


def snap(rows):
    return pd.DataFrame(rows, columns=["issuer", "isin", "net_short_pct", "position_date"]).assign(
        net_short_pct=lambda x: pd.to_numeric(x["net_short_pct"]))


def test_watchlist_keeps_recent_clusters_newest_first():
    df = pd.DataFrame([
        {"signal_date": "2026-11-20", "ticker": "AAA", "issuer": "A", "n_insiders": "2", "total_value": "150000"},
        {"signal_date": "2026-09-01", "ticker": "OLD", "issuer": "O", "n_insiders": "3", "total_value": "900000"},
        {"signal_date": "2026-11-18", "ticker": "BBB", "issuer": "B", "n_insiders": "4", "total_value": "2000000", "ret_5d": "0.031"},
    ])
    rows = d.watchlist(date(2026, 11, 21), clusters=df)
    assert [r["ticker"] for r in rows] == ["AAA", "BBB"]
    assert rows[1]["ret_5d"] == 0.031 and rows[0]["ret_5d"] is None
    assert rows[0]["total_value"] == 150000.0


def test_avoid_list_from_snapshots_flags_rises_of_half_a_point():
    snaps = {
        "2026-10-01": snap([["Up plc", "GB1", 0.6, ""], ["Flat plc", "GB2", 1.0, ""]]),
        "2026-11-21": snap([["Up plc", "GB1", 1.2, ""], ["Flat plc", "GB2", 1.3, ""], ["New plc", "GB3", 0.5, ""]]),
    }
    rows = d.avoid_list(date(2026, 11, 21), snaps=snaps, events=pd.DataFrame(), tickers={"GB1": "UP"})
    assert [r["isin"] for r in rows] == ["GB1", "GB3"]
    assert rows[0]["delta_pp"] == 0.6 and rows[0]["ticker"] == "UP"


def test_avoid_list_from_event_log_sums_rises():
    ev = pd.DataFrame([
        {"date": "2026-11-10", "event": "increase", "issuer": "X plc", "isin": "GBX", "prev_pct": "0.5", "new_pct": "0.8", "delta_pp": "0.3"},
        {"date": "2026-11-17", "event": "increase", "issuer": "X plc", "isin": "GBX", "prev_pct": "0.8", "new_pct": "1.1", "delta_pp": "0.3"},
        {"date": "2026-11-17", "event": "increase", "issuer": "Y plc", "isin": "GBY", "prev_pct": "0.5", "new_pct": "0.7", "delta_pp": "0.2"},
    ])
    rows = d.avoid_list(date(2026, 11, 21), snaps={}, events=ev, tickers={})
    assert [r["isin"] for r in rows] == ["GBX"]
    assert rows[0]["delta_pp"] == 0.6 and rows[0]["since"] == "2026-11-10"


def test_single_snapshot_gives_no_avoid_rows():
    snaps = {"2026-11-21": snap([["A plc", "GB1", 2.0, ""]])}
    assert d.avoid_list(date(2026, 11, 21), snaps=snaps, events=pd.DataFrame(), tickers={}) == []


def test_fetch_quote_uses_previous_close_and_survives_errors():
    q = d.fetch_quote("^FTSE", "FTSE 100", get=lambda *a, **k: Resp(chart(101.0, [99.0, 100.0, None, 101.0])))
    assert q["prev_close"] == 100.0 and round(q["change_pct"], 3) == 1.0
    assert d.fetch_quote("X", "X", get=lambda *a, **k: Resp({}, 404)) is None
    assert d.fetch_quote("X", "X", get=lambda *a, **k: Resp({"chart": {"result": None}})) is None


def test_rule_brief_frames_signals_as_watchlist_and_avoid():
    data = {"markets": {"uk_delayed": [{"symbol": "^FTSE", "change_pct": -0.4}], "us_reference": [{"symbol": "SPY", "change_pct": 0.8}]},
            "signals": {"watchlist": [{"ticker": "AAA", "issuer": "A", "n_insiders": 2, "total_value": 1.5e6}],
                        "avoid": [{"issuer": "Up plc", "delta_pp": 0.6, "new_pct": 1.2}], "combo": []}}
    text = d.rule_brief(data)
    assert "S&P 500 +0.8%" in text and "FTSE 100 -0.4%" in text
    assert "AAA" in text and "not buys" in text and "Up plc" in text and "avoid" in text


def test_build_data_without_keys_or_network(monkeypatch):
    monkeypatch.setattr(d, "load_snapshots", lambda: {})
    get = lambda url, **k: Resp(chart(10.0, [9.0, 10.0])) if "chart" in url else Resp({}, 404)
    data = d.build_data(today=date(2026, 11, 21), get=get, env={})
    assert data["brief"]["source"] == "rules" and data["brief"]["text"]
    assert data["analyst"] == {}
    assert len(data["markets"]["uk_delayed"]) == len(d.UK_QUOTES)
    json.dumps(data, default=str)


def test_previous_ai_brief_reused_only_for_same_day():
    payload = {"brief": {"source": "ai", "date": "2026-11-21", "text": "hello"}}
    get = lambda *a, **k: Resp(payload)
    assert d.previous_brief("u", date(2026, 11, 21), get) == "hello"
    assert d.previous_brief("u", date(2026, 11, 22), get) is None
    assert d.previous_brief(None, date(2026, 11, 21), get) is None


def test_build_copies_static_files(tmp_path, monkeypatch):
    monkeypatch.setattr(d, "build_data", lambda: {"signals": {"watchlist": [], "avoid": []}, "brief": {"source": "rules"}})
    out = d.main(tmp_path / "site")
    assert (out / "index.html").exists() and (out / "app.js").exists() and (out / "data.json").exists()


def test_feed_reads_json_and_sorts_avoid_first(tmp_path):
    p = tmp_path / "feed.json"
    p.write_text(json.dumps({"as_of": "2026-11-21", "disclaimer": "x", "signals": [
        {"date": "2026-11-20", "stance": "watch", "symbol": "A", "market": "US", "summary": "s", "evidence": "e"},
        {"date": "2026-11-19", "stance": "avoid", "symbol": "B", "market": "UK", "summary": "s", "evidence": "e"},
        {"date": "2026-11-21", "stance": "watch", "symbol": "C", "market": "US", "summary": "s", "evidence": "e"}]}))
    f = d.feed(p, tmp_path / "missing.md")
    assert [r["symbol"] for r in f["rows"]] == ["B", "C", "A"]
    assert f["track_record"] is None and f["as_of"] == "2026-11-21"
    assert d.feed(tmp_path / "nope.json") is None


class Done:
    def __init__(self, out, code=0):
        self.stdout, self.returncode = out, code


def test_cli_brief_uses_oauth_token(monkeypatch):
    monkeypatch.setattr(d.shutil, "which", lambda name: "/usr/bin/claude")
    seen = {}

    def run(cmd, **kw):
        seen.update(kw)
        return Done("Markets rose.\n")

    data = {"markets": {"uk_delayed": [], "us_reference": []}, "signals": {"watchlist": [], "avoid": []}}
    assert d.cli_brief(data, "tok", run=run) == "Markets rose."
    assert seen["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "tok" and "British spelling" in seen["input"]
    assert d.cli_brief(data, None, run=run) is None
    assert d.cli_brief(data, "tok", run=lambda *a, **k: Done("", 1)) is None
