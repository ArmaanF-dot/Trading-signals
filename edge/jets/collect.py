"""Daily jet collector: scan the newest adsb.lol days and list fresh flags.

adsb.lol publishes day D at about 03:30 UTC on D+1. Each run scans any of the last
CATCH_UP_DAYS days not yet saved, then writes signals/jets.json and signals/jets.md with
Omaha visits and first-time destinations of watchlist jets over the last FLAG_DAYS days.
These are information only ("info" stance): the study in reports/jets_study.md says whether
they carry any edge.
"""
import json
import os
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

import config
from edge.jets import day as D
from edge.jets import registry, study

CATCH_UP_DAYS = 7
FLAG_DAYS = 30
OUT_JSON = config.SIGNALS_DIR / "jets.json"
OUT_MD = config.SIGNALS_DIR / "jets.md"


def flags(h: pd.DataFrame, wl: pd.DataFrame, today: date, days: int = FLAG_DAYS) -> list[dict]:
    if h.empty:
        return []
    a = study.watch_arrivals(h, wl)
    ev = pd.concat([study.omaha_events(a), study.novel_events(a)], ignore_index=True)
    ev = ev[ev["date"] >= pd.Timestamp(today - timedelta(days=days))]
    out = []
    for r in ev.sort_values("date", ascending=False).itertuples():
        out.append({"date": r.date.strftime("%Y-%m-%d"), "kind": r.kind, "ticker": r.ticker, "company": r.company,
                    "jet": r.reg or r.hex, "airport": r.airport, "arrived_utc": r.arrived_utc, "stance": "info"})
    return out


def write(fl: list[dict], now: datetime) -> None:
    config.SIGNALS_DIR.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps({"generated_utc": now.strftime("%Y-%m-%dT%H:%MZ"), "flags": fl}, indent=1) + "\n")
    lines = ["# Corporate jet flags", "", f"Updated {now:%Y-%m-%d %H:%M} UTC. Information only; see reports/jets_study.md for "
             "whether these have predicted anything.", ""]
    if not fl:
        lines.append(f"No Omaha visits or first-time destinations in the last {FLAG_DAYS} days.")
    else:
        lines += ["| Date | Flag | Company | Jet | Airport |", "|---|---|---|---|---|"]
        label = {"omaha": "Omaha visit", "novel": "new destination"}
        lines += [f"| {f['date']} | {label.get(f['kind'], f['kind'])} | {f['company']} ({f['ticker']}) | {f['jet']} | {f['airport']} |" for f in fl]
    OUT_MD.write_text("\n".join(lines) + "\n")


def run(today: date | None = None) -> list[dict]:
    now = datetime.now(timezone.utc)
    today = today or now.date()
    wl_rows = registry.load()
    watch = {r["hex"] for r in wl_rows}
    airports = D.Airports.from_csv_text(requests.get(D.AIRPORTS_URL, timeout=120).text)
    token = os.environ.get("GITHUB_TOKEN")
    for k in range(CATCH_UP_DAYS, 0, -1):
        d = today - timedelta(days=k)
        if (D.HISTORY_DIR / f"{d.isoformat()}.csv").exists():
            continue
        try:
            rows, stats = D.run_day(d, watch, airports, token)
            if "error" not in stats:
                D.save(d, rows)
            print(f"{d}: {len(rows)} rows {stats}")
        except Exception as exc:
            print(f"{d} failed: {type(exc).__name__}: {exc}")
    fl = flags(study.load_history(), pd.DataFrame(wl_rows).fillna(""), today)
    write(fl, now)
    print(f"jets: {len(fl)} flags in the last {FLAG_DAYS} days")
    return fl
