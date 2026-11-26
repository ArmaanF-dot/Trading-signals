"""Bus departures for Baco's Travel card (build time, free, no key).

Source: bustimes.org, which republishes the national bus timetable (Bus Open Data) and, for
vehicles it can see, the expected time. For each configured stop we read today's and tomorrow's
departures, keep the services that go on to call somewhere whose name contains the destination
keyword (default "University"), and estimate the ride length from one sample trip per route.
The browser then works out "leave by" (departure minus the walk) and shows the next few.

Expected times are those at build time (every 30 minutes at most), so they are labelled as such;
the timetable itself is exact. Tube times are not fetched here: the browser asks TfL's open
API live, because those change every few seconds.
"""
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

import config

LONDON = ZoneInfo("Europe/London")
BASE = "https://bustimes.org"
UA = {"User-Agent": "Mozilla/5.0 (compatible; baco-dashboard; personal use)"}
MAX_PROBES = 8
TR = re.compile(r"<tr>(.*?)</tr>", re.S)
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s)).strip().replace("­", "")


def parse_stop_page(html: str, day: date) -> list[dict]:
    """Rows of a bustimes stop page: line, destination, scheduled and expected clock times, trip id.
    Rows have three cells (line, destination, time) or four when a live expected time is shown."""
    out = []
    for tr in TR.findall(html):
        tds = TD.findall(tr)
        if len(tds) < 3:
            continue
        m = re.search(r"(\d\d):(\d\d)", tds[2])
        if not m:
            continue
        trip = re.search(r"/trips/(\d+)", tds[2])
        e = re.search(r"(\d\d):(\d\d)", tds[3]) if len(tds) > 3 else None
        out.append({"line": _clean(tds[0]), "dest": _clean(re.sub(r'<div class="vehicle">.*?</div>', "", tds[1], flags=re.S)),
                    "day": day, "sched": (int(m[1]), int(m[2])), "expected": (int(e[1]), int(e[2])) if e else None,
                    "trip": trip[1] if trip else None})
    return out


def _utc(day: date, hm: tuple[int, int]) -> datetime:
    """Clock time at a stop (London) to UTC. Times past midnight roll into the next day."""
    d = day + timedelta(days=hm[0] // 24)
    return datetime(d.year, d.month, d.day, hm[0] % 24, hm[1], tzinfo=LONDON).astimezone(timezone.utc)


def _mins(t: str | None) -> int | None:
    m = re.match(r"(\d+):(\d\d)", t or "")
    return int(m[1]) * 60 + int(m[2]) if m else None


def ride_to(trip: dict, atco: str, keyword: str) -> tuple[str, int] | None:
    """(name of the first stop matching `keyword` after `atco`, minutes there) for one trip, else None."""
    times = trip.get("times") or []
    ids = [(t.get("stop") or {}).get("atco_code") for t in times]
    if atco not in ids:
        return None
    i = ids.index(atco)
    start = _mins(times[i].get("aimed_departure_time") or times[i].get("aimed_arrival_time"))
    for t in times[i + 1:]:
        name = (t.get("stop") or {}).get("name") or ""
        if keyword.lower() in name.lower():
            end = _mins(t.get("aimed_arrival_time") or t.get("aimed_departure_time"))
            if start is None or end is None:
                return name, 0
            return name, (end - start) % 1440
    return None


def departures(stop: dict, keyword: str, now: datetime | None = None, get=requests.get, days: int = 2) -> list[dict]:
    """Upcoming departures from one stop that go on to the destination keyword, soonest first."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(LONDON).date()
    rows = []
    for k in range(days):
        day = today + timedelta(days=k)
        try:
            r = get(f"{BASE}/stops/{stop['atco']}", params={"date": day.isoformat()}, headers=UA, timeout=25)
            if r.status_code == 200:
                rows += parse_stop_page(r.text, day)
        except requests.RequestException:
            continue
    verdict: dict[tuple[str, str], tuple[str, int] | None] = {}
    probes = 0
    for row in rows:                       # one sample trip per line and destination decides the route
        key = (row["line"], row["dest"])
        if key in verdict or not row["trip"] or probes >= MAX_PROBES:
            continue
        probes += 1
        try:
            r = get(f"{BASE}/api/trips/{row['trip']}/", headers=UA, timeout=25)
            verdict[key] = ride_to(r.json(), stop["atco"], keyword) if r.status_code == 200 else None
        except (requests.RequestException, ValueError):
            verdict[key] = None
    out = []
    for row in rows:
        v = verdict.get((row["line"], row["dest"]))
        if not v:
            continue
        dep = _utc(row["day"], row["sched"])
        exp = _utc(row["day"], row["expected"]) if row["expected"] else None
        if (exp or dep) < now - timedelta(minutes=1):
            continue
        out.append({"line": row["line"], "to": row["dest"], "calls_at": v[0], "ride_min": v[1],
                    "scheduled": dep.isoformat(timespec="minutes"), "expected": exp.isoformat(timespec="minutes") if exp else None,
                    "stop": stop["name"]})
    out.sort(key=lambda r: r["expected"] or r["scheduled"])
    return out


def build(now: datetime | None = None, get=requests.get, cfg: dict | None = None) -> dict:
    """The travel block for data.json: bus departures per configured stop plus the tube settings."""
    cfg = cfg or config.TRAVEL
    bus = cfg["bus"]
    stops = []
    for s in bus["stops"]:
        try:
            stops.append({"atco": s["atco"], "name": s["name"], "departures": departures(s, bus["destination_keyword"], now, get)[:40]})
        except Exception as exc:  # a broken source must not break the dashboard build
            print(f"travel: {s['atco']} failed: {type(exc).__name__}")
            stops.append({"atco": s["atco"], "name": s["name"], "departures": []})
    return {"bus": {"label": bus["label"], "walk_min": bus["walk_min"], "stops": stops,
                    "source": "bustimes.org (national bus timetable; expected times are as at the last build)"},
            "tube": cfg["tube"]}
