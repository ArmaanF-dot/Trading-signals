"""One day of adsb.lol history -> arrivals of watchlist jets, plus every arrival at Omaha.

Source: adsb.lol daily archive on GitHub (adsblol/globe_history_YYYY), ODbL 1.0, free, no key.
Each day is one release, tag v<YYYY.MM.DD>-planes-readsb-prod-0, split into tar parts
(.tar.aa, .tar.ab, ...), about 4 GB in all. We stream the parts straight into tarfile without
saving them, open only trace files (one per aircraft per day, gzip JSON in readsb's trace
format) and keep a few hundred rows.

adsb.lol does not apply the FAA's LADD block list, so LADD-blocked jets are visible here
(flightaware/FR24 hide them). PIA aircraft broadcast a temporary hex and cannot be linked to
their owner from public data.
"""
import csv
import gzip
import io
import json
import math
import re
import tarfile
from datetime import date, datetime, timezone
from pathlib import Path

import requests

import config

RELEASE_API = "https://api.github.com/repos/adsblol/globe_history_{year}/releases/tags/{tag}"
AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
HISTORY_DIR = config.DATA_DIR / "jets" / "history"
OMAHA = {"KOMA", "KMLE"}  # Eppley Airfield, Millard (Omaha's general-aviation field)
FIELDS = ["date", "hex", "reg", "type", "owner_op", "airport", "arrived_utc", "watch", "omaha"]
TRACE_NAME = re.compile(r"trace_full_(?:~)?([0-9a-f]{6})\.json$")
CELL = 0.1  # degrees, airport grid
MAX_KM = 4.0


def tag_for(day: date, pod: str = "prod-0") -> str:
    return f"v{day:%Y.%m.%d}-planes-readsb-{pod}"


class Airports:
    """Nearest airport lookup on a 0.1 degree grid."""

    def __init__(self, rows):
        self.grid: dict[tuple[int, int], list] = {}
        for r in rows:
            if r["type"] not in ("large_airport", "medium_airport", "small_airport"):
                continue
            try:
                lat, lon = float(r["latitude_deg"]), float(r["longitude_deg"])
            except ValueError:
                continue
            ident = r.get("gps_code") or r.get("icao_code") or r["ident"]
            self.grid.setdefault((int(lat // CELL), int(lon // CELL)), []).append((lat, lon, ident, r["type"]))

    @classmethod
    def from_csv_text(cls, text: str) -> "Airports":
        return cls(csv.DictReader(io.StringIO(text)))

    def nearest(self, lat: float, lon: float) -> str | None:
        ci, cj = int(lat // CELL), int(lon // CELL)
        best, best_d = None, MAX_KM
        rank = {"large_airport": 0, "medium_airport": 1, "small_airport": 2}
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for a in self.grid.get((ci + di, cj + dj), ()):
                    d = _km(lat, lon, a[0], a[1])
                    # prefer the bigger field when two are within 1 km of each other
                    if d < best_d - (1.0 if best and rank[a[3]] > rank[best[3]] else 0):
                        best, best_d = a, d
        return best[2] if best else None


def _km(a, b, c, d):
    p = math.pi / 180
    x = (d - b) * p * math.cos((a + c) / 2 * p)
    y = (c - a) * p
    return 6371 * math.hypot(x, y)


def arrivals(trace: dict, airports: Airports) -> list[tuple[str, float]]:
    """Airports the aircraft arrived at: the first slow or on-ground point after flying (ground
    speed over 150 kt), or the last low point before a gap of 30+ minutes or the end of the day
    (small fields often have no coverage on the ground)."""
    t0 = float(trace.get("timestamp", 0))
    out: list[tuple[str, float]] = []
    flying = False
    last_low = None
    prev_t = None
    pts = trace.get("trace") or []
    for p in pts:
        t, lat, lon, alt, gs = p[0], p[1], p[2], p[3], p[4]
        if prev_t is not None and t - prev_t > 1800 and flying and last_low:
            ap = airports.nearest(last_low[1], last_low[2])
            if ap:
                out.append((ap, t0 + last_low[0]))
                flying = False
        prev_t = t
        if lat is None or lon is None:
            continue
        on_ground = alt == "ground"
        if gs is not None and gs > 150 and not on_ground:
            flying = True
            last_low = None
            continue
        if not flying:
            continue
        if on_ground or (gs is not None and gs < 60):
            ap = airports.nearest(lat, lon)
            if ap:
                out.append((ap, t0 + t))
                flying = False
                last_low = None
        elif isinstance(alt, (int, float)) and alt < 4000:
            last_low = (t, lat, lon)
    if flying and last_low:
        ap = airports.nearest(last_low[1], last_low[2])
        if ap:
            out.append((ap, t0 + last_low[0]))
    # same field within 30 minutes counts once (touch-and-go, coverage flicker)
    dedup = []
    for ap, ts in out:
        if dedup and dedup[-1][0] == ap and ts - dedup[-1][1] < 1800:
            continue
        dedup.append((ap, ts))
    return dedup


def scan_tar(fileobj, day: date, watch: set[str], airports: Airports, omaha: set[str] = OMAHA) -> tuple[list[dict], dict]:
    rows, stats = [], {"traces": 0, "watch_seen": 0}
    with tarfile.open(fileobj=fileobj, mode="r|") as tf:
        for m in tf:
            if not m.isfile():
                continue
            mt = TRACE_NAME.search(m.name)
            if not mt:
                continue
            stats["traces"] += 1
            hx = mt[1]
            raw = tf.extractfile(m).read()
            in_watch = hx in watch
            try:
                body = gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw
            except OSError:
                continue
            # cheap pre-filter for the Omaha screen: Omaha's latitude must appear in the text
            if not in_watch and b",41." not in body:
                continue
            try:
                tr = json.loads(body)
            except ValueError:
                continue
            if not in_watch:
                pts = tr.get("trace") or []
                if not any(p[1] and 41.1 < p[1] < 41.5 and -96.3 < p[2] < -95.7 for p in pts):
                    continue
            if in_watch:
                stats["watch_seen"] += 1
            for ap, ts in arrivals(tr, airports):
                is_oma = ap in omaha
                if in_watch or is_oma:
                    rows.append({"date": day.isoformat(), "hex": hx, "reg": (tr.get("r") or "").strip(),
                                 "type": tr.get("t") or "", "owner_op": tr.get("ownOp") or "",
                                 "airport": ap, "arrived_utc": datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M"),
                                 "watch": int(in_watch), "omaha": int(is_oma)})
    return rows, stats


class _Concat(io.RawIOBase):
    """Read several HTTP responses back to back as one stream."""

    def __init__(self, urls, headers):
        self.urls, self.headers, self.cur = list(urls), headers, None

    def readable(self):
        return True

    def readinto(self, b):
        while True:
            if self.cur is None:
                if not self.urls:
                    return 0
                self.cur = requests.get(self.urls.pop(0), headers=self.headers, stream=True, timeout=120).raw
            n = self.cur.readinto(b)
            if n:
                return n
            self.cur = None


def part_urls(day: date, token: str | None = None) -> list[str]:
    hdr = {"Accept": "application/vnd.github+json"}
    if token:
        hdr["Authorization"] = f"Bearer {token}"
    for pod in ("prod-0", "staging-0"):
        r = requests.get(RELEASE_API.format(year=day.year, tag=tag_for(day, pod)), headers=hdr, timeout=60)
        if r.status_code == 200:
            assets = sorted((a["name"], a["browser_download_url"]) for a in r.json().get("assets", [])
                            if re.search(r"\.tar\.[a-z]{2}$", a["name"]))
            if assets:
                return [u for _, u in assets]
    return []


def run_day(day: date, watch: set[str], airports: Airports, token: str | None = None) -> tuple[list[dict], dict]:
    urls = part_urls(day, token)
    if not urls:
        return [], {"error": "no release"}
    stream = io.BufferedReader(_Concat(urls, {"User-Agent": "trading-signals research"}), buffer_size=1 << 22)
    rows, stats = scan_tar(stream, day, watch, airports)
    stats["parts"] = len(urls)
    return rows, stats


def save(day: date, rows: list[dict], out_dir: Path = HISTORY_DIR) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{day.isoformat()}.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return p
