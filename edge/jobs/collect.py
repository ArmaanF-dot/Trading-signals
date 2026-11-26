"""Daily snapshot of open job postings for US-listed companies on public ATS job boards.

Sources are the boards' own public JSON feeds, which exist so that companies can show their
openings on other sites: Greenhouse (boards-api.greenhouse.io), Lever (api.lever.co, robots.txt
allows crawling with a 1 s delay) and Ashby (api.ashbyhq.com posting API). One request per company
per day, at most one per JOBS_MIN_INTERVAL seconds, so the load is trivial.

Each run appends one row per company to data/jobs/daily.csv: open postings, postings added and
removed since the previous snapshot (by posting id). The previous ids live in data/jobs/state.json.
A failed fetch is logged with status "error" and leaves the stored ids alone, so a one-day outage
does not show up as every role being removed and re-added.
"""
import csv
import datetime as dt
import json
from pathlib import Path

import pandas as pd

import config
from edge import http

BOARDS_CSV = Path(__file__).with_name("boards.csv")
DAILY_COLS = ["date", "ticker", "ats", "token", "status", "open", "added", "removed"]

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
}


def load_boards(path=BOARDS_CSV) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def posting_ids(ats: str, payload) -> set[str]:
    """Posting ids from one board's JSON feed."""
    if ats == "greenhouse":
        return {str(j["id"]) for j in payload.get("jobs", [])}
    if ats == "lever":
        return {str(j["id"]) for j in payload}
    if ats == "ashby":
        return {str(j["id"]) for j in payload.get("jobs", []) if j.get("isListed", True)}
    raise ValueError(f"unknown ATS {ats}")


def fetch(ats: str, token: str, get=None):
    get = get or (lambda url: http.get(url, headers={"User-Agent": config.JOBS_USER_AGENT},
                                       min_interval=config.JOBS_MIN_INTERVAL).json())
    return get(URLS[ats].format(token=token))


def diff(prev: set[str] | None, now: set[str]) -> tuple[int, int | str, int | str]:
    """(open, added, removed); added/removed are blank on a company's first snapshot."""
    if prev is None:
        return len(now), "", ""
    return len(now), len(now - prev), len(prev - now)


def snapshot(boards: list[dict], state: dict, date: str, get=None, log=print) -> tuple[list[dict], dict]:
    rows, new_state = [], dict(state)
    for b in boards:
        row = {"date": date, "ticker": b["ticker"], "ats": b["ats"], "token": b["token"],
               "status": "ok", "open": "", "added": "", "removed": ""}
        try:
            ids = posting_ids(b["ats"], fetch(b["ats"], b["token"], get))
        except Exception as exc:  # one board's failure must not stop the others
            log(f"jobs {b['ticker']}: {type(exc).__name__}: {exc}")
            row["status"] = "error"
            rows.append(row)
            continue
        prev = state.get(b["ticker"])
        row["open"], row["added"], row["removed"] = diff(set(prev) if prev is not None else None, ids)
        new_state[b["ticker"]] = sorted(ids)
        rows.append(row)
    return rows, new_state


def run(today: str | None = None, get=None, data_dir: Path | None = None) -> pd.DataFrame:
    data_dir = Path(data_dir or config.JOBS_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today().isoformat()
    state_path, daily_path = data_dir / "state.json", data_dir / "daily.csv"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    daily = pd.read_csv(daily_path, dtype=str, keep_default_na=False) if daily_path.exists() else pd.DataFrame(columns=DAILY_COLS)
    if (daily["date"] == today).any():
        print(f"jobs: already have a snapshot for {today}")
        return daily[daily["date"] == today]
    rows, state = snapshot(load_boards(), state, today, get)
    new = pd.DataFrame(rows, columns=DAILY_COLS).astype(str)
    pd.concat([daily, new], ignore_index=True).to_csv(daily_path, index=False)
    state_path.write_text(json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n")
    ok = new[new["status"] == "ok"]
    print(f"jobs: {len(ok)}/{len(new)} boards read, {pd.to_numeric(ok['open']).sum():.0f} open postings")
    return new
