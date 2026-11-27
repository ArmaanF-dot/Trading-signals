import gzip
import io
import json
import tarfile
import zipfile
from datetime import date

from edge.jets import day as D
from edge.jets import registry as R

AIRPORTS = """id,ident,type,name,latitude_deg,longitude_deg,elevation_ft,continent,iso_country,iso_region,municipality,scheduled_service,icao_code,iata_code,gps_code,local_code,home_link,wikipedia_link,keywords
1,KOMA,large_airport,Eppley,41.3032,-95.894096,984,NA,US,US-NE,Omaha,yes,KOMA,OMA,KOMA,OMA,,,
2,KTEB,medium_airport,Teterboro,40.85,-74.0608,9,NA,US,US-NJ,Teterboro,no,KTEB,TEB,KTEB,TEB,,,
3,KXXX,heliport,Pad,40.851,-74.061,9,NA,US,US-NJ,X,no,,,KXXX,,,,
"""


def _trace(lat0, lon0, lat1, lon1):
    pts = [[0, lat0, lon0, "ground", 10, 0, 0, 0, None],
           [600, (lat0 + lat1) / 2, (lon0 + lon1) / 2, 40000, 450, 0, 0, 0, None],
           [3600, lat1 + 0.05, lon1, 3000, 160, 0, 0, 0, None],
           [3800, lat1, lon1, "ground", 40, 0, 0, 0, None]]
    return {"icao": "x", "r": "N1", "t": "GLF6", "ownOp": "ACME INC", "timestamp": 1718150400.0, "trace": pts}


def test_arrivals_detects_landing_and_ignores_heliport():
    ap = D.Airports.from_csv_text(AIRPORTS)
    assert D.arrivals(_trace(40.85, -74.06, 41.3032, -95.8941), ap) == [("KOMA", 1718150400.0 + 3800)]
    assert ap.nearest(40.851, -74.061) == "KTEB"
    assert ap.nearest(10, 10) is None


def test_arrival_before_coverage_gap():
    ap = D.Airports.from_csv_text(AIRPORTS)
    tr = {"timestamp": 0, "trace": [[0, 41.0, -90.0, 30000, 450], [1000, 40.86, -74.06, 1500, 140],
                                    [5000, 40.85, -74.06, "ground", 5]]}
    assert [a for a, _ in D.arrivals(tr, ap)] == ["KTEB"]


def _tar(traces: dict) -> io.BytesIO:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for hx, tr in traces.items():
            raw = gzip.compress(json.dumps(tr, separators=(",", ":")).encode())
            ti = tarfile.TarInfo(f"./traces/{hx[-2:]}/trace_full_{hx}.json")
            ti.size = len(raw)
            tf.addfile(ti, io.BytesIO(raw))
    buf.seek(0)
    return buf


def test_scan_tar_keeps_watchlist_and_omaha_only():
    ap = D.Airports.from_csv_text(AIRPORTS)
    tar = _tar({"a00001": _trace(41.3, -95.9, 40.85, -74.06),   # watchlist jet to Teterboro
                "a00002": _trace(40.85, -74.06, 41.3032, -95.8941),  # stranger to Omaha
                "a00003": _trace(41.3, -95.9, 40.85, -74.06)})  # stranger elsewhere
    rows, stats = D.scan_tar(tar, date(2024, 6, 12), {"a00001"}, ap)
    got = {(r["hex"], r["airport"], r["watch"], r["omaha"]) for r in rows}
    assert got == {("a00001", "KTEB", 1, 0), ("a00002", "KOMA", 0, 1)}
    assert stats["traces"] == 3 and stats["watch_seen"] == 1


def _faa_zip():
    ref = "CODE,MFR,MODEL,TYPE-ACFT,TYPE-ENG,AC-CAT\nJ1,GULFSTREAM,G650,5,5,1\nP1,CESSNA,172,4,1,1\n"
    master_head = "N-NUMBER,NAME,CITY,STATE,MFR MDL CODE,MODE S CODE HEX\n"
    master = master_head + "\n".join([
        "100A,NIKE INC,BEAVERTON,OR,J1,A00001",
        "100B,FRANKLIN TEMPLETON TRAVEL INC,SAN MATEO,CA,J1,A00002",
        "100C,MORGAN FLIGHT LLC,X,TX,J1,A00003",
        "100D,BANK OF UTAH TRUSTEE,SLC,UT,J1,A00004",
        "100E,NIKE INC,BEAVERTON,OR,P1,A00005",
        "100F,UNITED AIRLINES INC,CHICAGO,IL,J1,A00006"]) + "\n"
    dereg = "N-NUMBER,NAME,CITY-MAIL,STATE-ABBREV-MAIL,MFR-MDL-CODE,CANCEL-DATE,MODE S CODE HEX\n" \
            "200A,WALMART INC,BENTONVILLE,AR,J1,20240301,A00007\n200B,WALMART INC,BENTONVILLE,AR,J1,20190301,A00008\n"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ACFTREF.txt", ref)
        z.writestr("MASTER.txt", master)
        z.writestr("DEREG.txt", dereg)
    return buf.getvalue()


def test_watchlist_matching():
    tickers = {"0": {"ticker": "NKE", "title": "NIKE, Inc."}, "1": {"ticker": "BEN", "title": "FRANKLIN TEMPLETON INC"},
               "2": {"ticker": "MGHL", "title": "MORGAN GROUP HOLDING CO"}, "3": {"ticker": "WMT", "title": "Walmart Inc."},
               "4": {"ticker": "UAL", "title": "United Airlines Holdings"}}
    rows = {r["hex"]: r for r in R.build(_faa_zip(), tickers)}
    assert set(rows) == {"a00001", "a00002", "a00007"}
    assert rows["a00001"]["ticker"] == "NKE" and rows["a00002"]["ticker"] == "BEN"
    assert rows["a00007"]["valid_to"] == "2024-03-01"


# --- study ---
import pandas as pd

from edge.jets import study as S


def _arr(rows):
    df = pd.DataFrame(rows, columns=["date", "hex", "airport", "ticker", "company", "state"])
    df["date"] = pd.to_datetime(df["date"])
    df["arrived_utc"] = df["date"].dt.strftime("%Y-%m-%dT12:00")
    df["reg"] = ""
    return df


def test_novel_needs_history_and_skips_home():
    rows = [("2024-01-01", "a1", "KHOM", "X", "X", "TX")]
    rows += [(f"2024-0{m}-01", "a1", "KHOM", "X", "X", "TX") for m in range(2, 9)]
    rows += [("2024-02-01", "a1", "KAAA", "X", "X", "TX"),   # too early: under 180 days of history
             ("2024-08-15", "a1", "KBBB", "X", "X", "TX"),   # new airport after 180 days -> event
             ("2024-08-18", "a1", "KCCC", "X", "X", "TX"),   # within 7 days of the last event -> thinned
             ("2024-09-01", "a1", "KBBB", "X", "X", "TX")]   # seen recently -> not novel
    ev = S.novel_events(_arr(rows))
    assert list(ev["airport"]) == ["KBBB"]


def test_omaha_excludes_nebraska_and_thins():
    a = _arr([("2024-03-01", "a1", "KOMA", "X", "X", "TX"), ("2024-03-10", "a1", "KOMA", "X", "X", "TX"),
              ("2024-05-01", "a1", "KMLE", "X", "X", "TX"), ("2024-03-01", "a2", "KOMA", "U", "U", "NE")])
    ev = S.omaha_events(a)
    assert list(ev["date"].dt.strftime("%m-%d")) == ["03-01", "05-01"] and set(ev["ticker"]) == {"X"}


def test_deal_dates_and_base_rate():
    fl = pd.DataFrame({"form": ["8-K", "8-K", "425", "10-Q"], "items": ["2.01,9.01", "2.02", "", ""],
                       "filed": pd.to_datetime(["2024-03-01", "2024-04-01", "2024-06-01", "2024-07-01"])})
    dd = S.deal_dates(fl)
    assert dd == [pd.Timestamp("2024-03-01"), pd.Timestamp("2024-06-01")]
    assert S.deal_hit(dd, pd.Timestamp("2024-01-15")) and not S.deal_hit(dd, pd.Timestamp("2024-06-01"))
    assert 0 < S.base_rate(dd, pd.Timestamp("2024-01-01"), pd.Timestamp("2024-12-31")) < 1


def test_issuers_from_13f():
    xml = ('<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">'
           '<infoTable><nameOfIssuer>OCCIDENTAL PETE CORP</nameOfIssuer></infoTable>'
           '<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer></infoTable></informationTable>')
    assert S.issuers_from_13f(xml) == {"OCCIDENTAL PETE", "APPLE"}


def test_collect_flags_recent_only():
    from datetime import date
    from edge.jets import collect
    h = pd.DataFrame({"date": pd.to_datetime(["2024-03-01", "2024-06-01"]), "hex": ["a1", "a1"], "reg": ["N1", "N1"],
                      "type": ["GLF6"] * 2, "owner_op": [""] * 2, "airport": ["KOMA", "KOMA"],
                      "arrived_utc": ["2024-03-01T12:00", "2024-06-01T12:00"], "watch": [1, 1], "omaha": [1, 1]})
    wl = pd.DataFrame({"hex": ["a1"], "ticker": ["X"], "company": ["X CORP"], "state": ["TX"], "city": ["D"], "valid_to": [""]})
    fl = collect.flags(h, wl, date(2024, 6, 10))
    assert [(f["date"], f["kind"]) for f in fl] == [("2024-06-01", "omaha")]
