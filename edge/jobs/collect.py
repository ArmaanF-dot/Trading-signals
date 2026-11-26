"""Daily snapshot of open job postings for US-listed companies on public ATS job boards.

Sources are the boards' own public JSON feeds, which exist so that companies can show their
openings on other sites: Greenhouse (boards-api.greenhouse.io), Lever (api.lever.co, robots.txt
allows crawling with a 1 s delay) and Ashby (api.ashbyhq.com posting API). One request per company
per day, at most one per JOBS_MIN_INTERVAL seconds, so the load is trivial.

Each run appends one row per company to data/jobs/daily.csv: open postings, postings added and
removed since the previous snapshot (by posting id). The previous ids live in data/jobs/state.json.
A failed fetch is logged with status "error" and leaves the stored ids alone, so a one-day outage
does not show up as every role being removed and re-added.

Workday boards (most large non-tech employers) are read through the same JSON endpoint their public
careers page calls. Workday reports at most 2,000 open roles (status "capped" when it hits that), and
listing every id would take up to 100 requests, so for Workday we record the total and the number of
roles shown as posted today on the first few pages (approximate: it assumes newest-first order) as "added", and leave "removed" blank.
"""
import csv
import time
import datetime as dt
import json
from pathlib import Path

import pandas as pd
import requests

import config
from edge import http

BOARDS_CSV = Path(__file__).with_name("boards.csv")
DAILY_COLS = ["date", "ticker", "ats", "token", "status", "open", "added", "removed", "eng", "sales"]
WORKDAY_CAP = 2000
WORKDAY_PAGES = 5

URLS = {
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    "lever": "https://api.lever.co/v0/postings/{token}?mode=json",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{token}",
    "workday": None,  # POST, see workday_snapshot
}


def load_boards(path=BOARDS_CSV) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def postings(ats: str, payload) -> dict[str, str]:
    """{posting id: title} from one board's JSON feed."""
    if ats == "greenhouse":
        return {str(j["id"]): str(j.get("title", "")) for j in payload.get("jobs", [])}
    if ats == "lever":
        return {str(j["id"]): str(j.get("text", "")) for j in payload}
    if ats == "ashby":
        return {str(j["id"]): str(j.get("title", "")) for j in payload.get("jobs", []) if j.get("isListed", True)}
    raise ValueError(f"unknown ATS {ats}")


def posting_ids(ats: str, payload) -> set[str]:
    return set(postings(ats, payload))


def function_counts(titles) -> tuple[int, int]:
    from edge.jobs.deep import classify
    kinds = [classify(t) for t in titles]
    return kinds.count("eng"), kinds.count("sales")


def workday_url(token: str) -> str:
    """token is 'tenant.wdN/site', e.g. 'abbott.wd5/abbottcareers'."""
    host, site = token.split("/", 1)
    tenant = host.split(".")[0]
    return f"https://{host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"


def _post(url: str, body: dict, tries: int = 3) -> dict:
    """POST with a pause first; on 429 (Workday's rate limit) wait and try again."""
    wait = 30.0
    for attempt in range(tries):
        time.sleep(config.JOBS_WORKDAY_INTERVAL)
        r = requests.post(url, json=body, headers={"User-Agent": config.JOBS_USER_AGENT, "Accept": "application/json"},
                          timeout=config.HTTP_TIMEOUT)
        if r.status_code == 429 and attempt < tries - 1:
            time.sleep(wait)
            wait *= 2
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("unreachable")


def workday_snapshot(token: str, post=None) -> dict:
    """Total open roles, roles posted today, and engineering/sales counts among the pages read."""
    post = post or _post
    url = workday_url(token)
    total, today, titles = None, 0, []
    for page in range(WORKDAY_PAGES):
        js = post(url, {"limit": 20, "offset": 20 * page, "appliedFacets": {}, "searchText": ""})
        if total is None:
            total = int(js.get("total") or 0)
        jobs = js.get("jobPostings") or []
        titles += [j.get("title", "") for j in jobs]
        fresh = [j for j in jobs if str(j.get("postedOn", "")).lower() == "posted today"]
        today += len(fresh)
        if len(fresh) < len(jobs) or not jobs:
            break
    eng, sales = function_counts(titles)
    return {"open": total or 0, "added": today, "status": "capped" if (total or 0) >= WORKDAY_CAP else "ok",
            "eng": eng, "sales": sales}


def fetch(ats: str, token: str, get=None):
    get = get or (lambda url: http.get(url, headers={"User-Agent": config.JOBS_USER_AGENT},
                                       min_interval=config.JOBS_MIN_INTERVAL).json())
    return get(URLS[ats].format(token=token))


def diff(prev: set[str] | None, now: set[str]) -> tuple[int, int | str, int | str]:
    """(open, added, removed); added/removed are blank on a company's first snapshot."""
    if prev is None:
        return len(now), "", ""
    return len(now), len(now - prev), len(prev - now)


def snapshot(boards: list[dict], state: dict, date: str, get=None, log=print, post=None) -> tuple[list[dict], dict]:
    rows, new_state = [], dict(state)
    for b in boards:
        row = {"date": date, "ticker": b["ticker"], "ats": b["ats"], "token": b["token"],
               "status": "ok", "open": "", "added": "", "removed": "", "eng": "", "sales": ""}
        try:
            if b["ats"] == "workday":
                row.update(workday_snapshot(b["token"], post))
                rows.append(row)
                continue
            jobs = postings(b["ats"], fetch(b["ats"], b["token"], get))
            ids = set(jobs)
            row["eng"], row["sales"] = function_counts(jobs.values())
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


def run(today: str | None = None, get=None, data_dir: Path | None = None, post=None) -> pd.DataFrame:
    data_dir = Path(data_dir or config.JOBS_DIR)
    data_dir.mkdir(parents=True, exist_ok=True)
    today = today or dt.date.today().isoformat()
    state_path, daily_path = data_dir / "state.json", data_dir / "daily.csv"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    daily = pd.read_csv(daily_path, dtype=str, keep_default_na=False) if daily_path.exists() else pd.DataFrame(columns=DAILY_COLS)
    daily = daily.reindex(columns=DAILY_COLS, fill_value="")  # files written before a column was added
    if (daily["date"] == today).any():
        print(f"jobs: already have a snapshot for {today}")
        return daily[daily["date"] == today]
    rows, state = snapshot(load_boards(), state, today, get, post=post)
    new = pd.DataFrame(rows, columns=DAILY_COLS).astype(str)
    pd.concat([daily, new], ignore_index=True).to_csv(daily_path, index=False)
    state_path.write_text(json.dumps(state, separators=(",", ":"), sort_keys=True) + "\n")
    ok = new[new["status"] != "error"]
    print(f"jobs: {len(ok)}/{len(new)} boards read, {pd.to_numeric(ok['open']).sum():.0f} open postings")
    return new
