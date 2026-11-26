"""Offline tests for Baco's calendar, headlines, bus times and UFC interface."""
import json
from datetime import date, datetime, timezone

from edge import events, travel, ufc


class Resp:
    def __init__(self, payload=None, text="", status=200):
        self.payload, self.text, self.status_code = payload, text, status

    def json(self):
        return self.payload


def test_earnings_keeps_big_names_and_watched_tickers():
    rows = [
        {"symbol": "BIG", "name": "Big Co", "marketCap": "$150,000,000,000", "time": "time-pre-market", "epsForecast": "($0.38)", "noOfEsts": "9", "fiscalQuarterEnding": "Oct/2026"},
        {"symbol": "TINY", "name": "Tiny Co", "marketCap": "$300,000,000", "time": "time-after-hours"},
        {"symbol": "MINE", "name": "Mine Co", "marketCap": "$500,000,000", "time": "time-not-supplied"},
    ]
    get = lambda url, **kw: Resp({"data": {"rows": rows}})
    out = events.earnings(date(2026, 11, 30), get, extra={"mine"}, days=0, pause=0)   # a Monday
    assert [r["symbol"] for r in out] == ["BIG", "MINE"]
    assert out[0]["time"] == "Before open" and out[0]["eps_forecast"] == -0.38 and out[0]["market_cap"] == 150e9
    assert out[1]["watch"] is True


def test_earnings_skips_weekends_and_survives_errors():
    def get(url, **kw):
        raise events.requests.RequestException("down")
    assert events.earnings(date(2026, 11, 28), get, days=1, pause=0) == []   # Saturday and Sunday


def test_macro_filters_currency_and_impact_and_converts_to_utc():
    items = [
        {"title": "CPI", "country": "USD", "date": "2026-12-10T08:30:00-05:00", "impact": "High", "forecast": "0.3%", "previous": "0.2%"},
        {"title": "Minor", "country": "USD", "date": "2026-12-10T09:00:00-05:00", "impact": "Low"},
        {"title": "Yen thing", "country": "JPY", "date": "2026-12-10T09:00:00-05:00", "impact": "High"},
    ]
    out = events.macro(lambda url, **kw: Resp(items))
    assert len(out) == 1 and out[0]["when"] == "2026-12-10T13:30+00:00" and out[0]["forecast"] == "0.3%"


RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Older</title><link>https://example.com/a</link><pubDate>Wed, 25 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>Newer</title><link>https://example.com/b</link><pubDate>Thu, 26 Nov 2026 01:00:00 +0000</pubDate></item>
<item><title>No link</title><link></link></item></channel></rss>"""


def test_news_sorted_newest_first_and_drops_bad_items():
    out = events.news(lambda url, **kw: Resp(text=RSS), per_feed=5)
    assert out[0]["title"] == "Newer" and "No link" not in [n["title"] for n in out]
    assert all(n["link"].startswith("http") for n in out)


STOP_HTML = """<table><tbody>
<tr><td class="nowrap"><a href="/s/u1">U1</a></td><td>University of Warwick <div class="vehicle"><a href="/v">1 - X</a></div></td><td><a href="/map#journey=1"> 08:13 </a></td><td><a href="/map#journey=1"> 08:20 </a></td></tr>
<tr><td class="nowrap"><a href="/s/665">665</a></td><td>Bishop's Itchington</td><td><a href="/trips/99"> 08:30 </a></td></tr>
<tr><td class="nowrap"><a href="/s/u1">U1</a></td><td>University of Warwick</td><td><a href="/trips/42"> 08:43 </a></td></tr>
</tbody></table>"""


def test_parse_stop_page_handles_three_and_four_cell_rows():
    rows = travel.parse_stop_page(STOP_HTML, date(2026, 11, 30))
    assert [(r["line"], r["sched"], r["expected"], r["trip"]) for r in rows] == [
        ("U1", (8, 13), (8, 20), None), ("665", (8, 30), None, "99"), ("U1", (8, 43), None, "42")]
    assert rows[0]["dest"] == "University of Warwick"


def test_ride_to_finds_university_after_the_stop_only():
    trip = {"times": [
        {"stop": {"atco_code": "X", "name": "Somewhere"}, "aimed_departure_time": "08:40", "aimed_arrival_time": None},
        {"stop": {"atco_code": "Y", "name": "Gibbet Hill"}, "aimed_departure_time": "08:55"},
        {"stop": {"atco_code": "Z", "name": "University Interchange"}, "aimed_arrival_time": "09:05", "aimed_departure_time": None}]}
    assert travel.ride_to(trip, "X", "University") == ("University Interchange", 25)
    assert travel.ride_to(trip, "Z", "University") is None       # nothing after it
    assert travel.ride_to(trip, "NOPE", "University") is None


def test_bus_departures_keep_only_university_bound_routes():
    trips = {"42": {"times": [{"stop": {"atco_code": "S", "name": "Wheatsheaf"}, "aimed_departure_time": "08:43"},
                              {"stop": {"atco_code": "U", "name": "University Interchange"}, "aimed_arrival_time": "09:10"}]},
             "99": {"times": [{"stop": {"atco_code": "S", "name": "Wheatsheaf"}, "aimed_departure_time": "08:30"},
                              {"stop": {"atco_code": "B", "name": "Bishops Hill"}, "aimed_arrival_time": "08:50"}]}}

    def get(url, **kw):
        if "/api/trips/" in url:
            return Resp(trips[url.rstrip("/").split("/")[-1]])
        return Resp(text=STOP_HTML)

    now = datetime(2026, 11, 30, 8, 0, tzinfo=timezone.utc)      # GMT in winter, so London time equals UTC
    out = travel.departures({"atco": "S", "name": "Wheatsheaf"}, "University", now, get, days=1)
    assert [d["line"] for d in out] == ["U1", "U1"]          # the live-tracked 08:13 (due 08:20) and the 08:43; the 665 is dropped
    assert out[0]["expected"] == "2026-11-30T08:20+00:00" and out[1]["scheduled"] == "2026-11-30T08:43+00:00" and out[1]["ride_min"] == 27


def test_bus_times_roll_into_next_day_and_summer_time():
    assert travel._utc(date(2026, 7, 1), (8, 0)).isoformat() == "2026-07-01T07:00:00+00:00"
    assert travel._utc(date(2026, 11, 30), (24, 10)).isoformat() == "2026-12-01T00:10:00+00:00"


RAW = {"asof": "2026-11-26T10:00", "forward": {"logged": 3, "graded": 1, "needed": 150}, "evidence": [{"label": "x", "v": 1.0, "lo": -2, "hi": 4, "n": "10", "kind": "test"}],
       "cards": [{"name": "UFC Test", "dates": ["2026-12-05"], "days": 9, "last_data": "2026-11-21", "fights": [
           {"a": "A One", "b": "B Two", "wc": "Lightweight", "rounds": 5, "p_model": 0.31, "p_blend": 0.4, "p_mkt": 0.45, "p_elo": 0.4, "dist": 0.5, "flags": [], "coverage": [5, 2],
            "drivers": [["Reach", 3.14159], ["Age", -1]], "pick": {"tier": "70-80"}, "best_a": 3.1, "best_a_book": "BookA", "best_b": 1.4, "best_b_book": "BookB",
            "bet": {"fighter": "B Two", "price": 1.4, "book": "BookB", "edge": 0.06, "stake": 4.2}}]}]}


def test_ufc_public_export_has_no_prices_and_privates_do():
    pub = ufc.normalise(RAW, public=True)
    f = pub["events"][0]["fights"][0]
    assert f["pick"] == "B Two" and f["confidence"] == 0.69 and f["confidence_label"] == "Moderate" and f["thin_data"] is True
    assert not ({"price_a", "price_b", "market_p_a", "bet", "book_a"} & set(f))
    assert "BookA" not in json.dumps(pub) and "stake" not in json.dumps(pub)
    priv = ufc.normalise(RAW, public=False)["events"][0]["fights"][0]
    assert priv["price_a"] == 3.1 and priv["bet"]["stake_per_50"] == 4.2


def test_ufc_load_rejects_wrong_schema(tmp_path):
    p = tmp_path / "u.json"
    p.write_text(json.dumps(ufc.normalise(RAW)))
    assert ufc.load(p)["events"][0]["name"] == "UFC Test"
    p.write_text(json.dumps({"schema": 99, "events": []}))
    assert ufc.load(p) is None and ufc.load(tmp_path / "missing.json") is None


def test_tier_labels():
    assert [ufc.tier_label(x) for x in (0.9, 0.75, 0.65, 0.55, None)] == ["High", "Good", "Moderate", "Toss-up", "Unknown"]


def test_build_data_survives_failing_optional_sources(monkeypatch):
    from edge import dashboard as d
    monkeypatch.setattr(d.events, "news", lambda get: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(d.travel, "build", lambda **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    assert d.safe(lambda: d.events.news(None), []) == []
    assert d.safe(lambda: d.travel.build(), None) is None
