"""Watchlist of business jets registered to US-listed companies (FAA registry + SEC names).

The FAA releasable aircraft database (public record, free) gives owner name and Mode S hex
for every US-registered aircraft. We keep turbofan fixed-wing aircraft whose registered owner
matches an SEC-listed company name, either exactly ("NIKE INC") or as a flight-department
variant ("NIKE AVIATION LLC"). Airlines, cargo carriers, manufacturers and dealers are dropped.

What this misses, by design of the registry: jets held through a bank trustee (BANK OF UTAH
TRUSTEE and similar, ~4,000 jets), anonymous LLCs, fractional/charter (NetJets, Flexjet) and
foreign registrations. Most large-cap CEOs fly that way, so coverage is partial and biased
toward companies that do not bother hiding.

Deregistered aircraft (DEREG.txt) with a cancel date in the study window are included with a
valid_to date, so a jet sold in 2024 still counts for its 2023 flights.
"""
import csv
import io
import json
import re
import zipfile
from pathlib import Path

import requests

import config

FAA_URL = "https://registry.faa.gov/database/ReleasableAircraft.zip"
# The FAA site rejects non-browser user agents.
FAA_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
OUT = config.DATA_DIR / "jets" / "watchlist.csv"
COLUMNS = ["hex", "n_number", "owner", "ticker", "company", "city", "state", "model", "valid_to"]

STOP = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LLC", "LP", "PLC", "THE", "HOLDINGS",
        "HOLDING", "GROUP", "INCORPORATED", "NV", "SA", "AG", "DE", "NEW", "OF", "AND", "LIMITED"}
FLIGHT_WORDS = {"AVIATION", "AIR", "AIRCRAFT", "FLIGHT", "FLIGHTS", "TRANSPORTATION", "TRANSPORT",
                "AIRWING", "AVIATION SERVICES", "FLIGHT DEPARTMENT", "FLIGHT OPERATIONS", "JET", "JETS",
                "AIR TRANSPORT", "AIR SERVICES", "AVIATION SERVICES", "TRAVEL"}
EXCLUDE = re.compile(r"AIRLINES|AIRWAYS|AIR LINES|FEDERAL EXPRESS|PARCEL|AEROSPACE|BOEING|TEXTRON|SKYWEST|"
                     r"ATLAS AIR|AMAZON|EMBRAER|BOMBARDIER|DASSAULT|CESSNA|HONDA AIRCRAFT|AERSALE|WILLIS LEASE|"
                     r"AIR LEASE|AERCAP|TRUSTEE|BANK|FLEXJET|NETJETS|WHEELS UP|CHARTER|SURF AIR|BLADE|JOBY")
# SEC names too generic to match safely on their own
GENERIC_MIN_LEN = 6


def norm(name: str) -> str:
    s = name.upper().replace("&", " ")
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return " ".join(w for w in s.split() if w not in STOP)


def strip_flight_words(n: str) -> str:
    words = n.split()
    while words and words[-1] in {w for f in FLIGHT_WORDS for w in f.split()} | {"SERVICES", "DEPARTMENT", "OPERATIONS"}:
        words.pop()
    return " ".join(words)


def sec_index(tickers: dict) -> dict[str, tuple[str, str]]:
    """normalised company name -> (ticker, title); first (largest) listing wins."""
    out: dict[str, tuple[str, str]] = {}
    for t in tickers.values():
        n = norm(t["title"])
        if len(n) >= GENERIC_MIN_LEN or " " in n:
            out.setdefault(n, (t["ticker"], t["title"]))
    return out


def match_owner(owner: str, sec: dict) -> tuple[str, str] | None:
    if not owner or EXCLUDE.search(owner.upper()):
        return None
    n = norm(owner)
    if n in sec:
        return sec[n]
    base = strip_flight_words(n)
    # flight-department variants ("FRANKLIN TEMPLETON TRAVEL INC") only for distinctive multi-word
    # names; single words like MORGAN or COSMOS matched unrelated LLCs in testing.
    if base != n and base in sec and " " in base and len(base) >= 10:
        return sec[base]
    return None


def _rows(text: str):
    r = csv.reader(io.StringIO(text))
    head = [h.strip().lstrip("﻿") for h in next(r)]
    for row in r:
        yield {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(head)}


def build(faa_zip: bytes, tickers: dict, since: str = "20230101") -> list[dict]:
    z = zipfile.ZipFile(io.BytesIO(faa_zip))
    read = lambda n: z.read(n).decode("utf-8-sig", errors="replace")
    ref = {r["CODE"]: r for r in _rows(read("ACFTREF.txt"))}
    sec = sec_index(tickers)

    def is_jet(code: str) -> bool:
        a = ref.get(code)
        return bool(a) and a.get("TYPE-ACFT") == "5" and a.get("TYPE-ENG") == "5"

    def model(code: str) -> str:
        a = ref.get(code, {})
        return f"{a.get('MFR', '')} {a.get('MODEL', '')}".strip()

    out = {}
    for r in _rows(read("MASTER.txt")):
        if not is_jet(r["MFR MDL CODE"]):
            continue
        m = match_owner(r["NAME"], sec)
        if m and r["MODE S CODE HEX"]:
            out[r["MODE S CODE HEX"].lower()] = {
                "hex": r["MODE S CODE HEX"].lower(), "n_number": "N" + r["N-NUMBER"], "owner": r["NAME"],
                "ticker": m[0], "company": m[1], "city": r["CITY"], "state": r["STATE"],
                "model": model(r["MFR MDL CODE"]), "valid_to": ""}
    for r in _rows(read("DEREG.txt")):
        hx = r.get("MODE S CODE HEX", "").lower()
        if not hx or hx in out or r.get("CANCEL-DATE", "") < since or not is_jet(r["MFR-MDL-CODE"]):
            continue
        m = match_owner(r["NAME"], sec)
        if m:
            c = r["CANCEL-DATE"]
            out[hx] = {"hex": hx, "n_number": "N" + r["N-NUMBER"], "owner": r["NAME"], "ticker": m[0],
                       "company": m[1], "city": r["CITY-MAIL"], "state": r["STATE-ABBREV-MAIL"],
                       "model": model(r["MFR-MDL-CODE"]), "valid_to": f"{c[:4]}-{c[4:6]}-{c[6:]}"}
    return sorted(out.values(), key=lambda d: (d["ticker"], d["hex"]))


def load(path: Path = OUT) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def run() -> list[dict]:
    faa = requests.get(FAA_URL, headers=FAA_UA, timeout=300).content
    ua = config.os.environ.get("SEC_USER_AGENT") or "trading-signals research bot"
    tickers = requests.get(SEC_TICKERS_URL, headers={"User-Agent": ua}, timeout=60).json()
    rows = build(faa, tickers)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"watchlist: {len(rows)} jets, {len({r['ticker'] for r in rows})} companies -> {OUT}")
    return rows
