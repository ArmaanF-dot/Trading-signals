import io
import zipfile

import pandas as pd

import config
from edge.form4 import backtest as bt

SUB = ("ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL\n"
       "A1\t05-JAN-2024\t4\t111\tAcme\tacme\nA2\t09-JAN-2024\t4\t111\tAcme\tacme\nA3\t09-JAN-2024\t3\t111\tAcme\tacme\n")
OWN = ("ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE\n"
       "A1\t1\tJane\tDirector,Officer\tCEO\nA2\t2\tBob\tOfficer\tCFO\nA3\t3\tX\tDirector\t\n")
TX = ("ACCESSION_NUMBER\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD\n"
      "A1\t03-JAN-2024\tP\t10000\t5\tA\nA2\t08-JAN-2024\tP\t10000\t5\tA\nA2\t08-JAN-2024\tS\t100\t5\tD\nA3\t08-JAN-2024\tP\t5\t5\tA\n")


def make_zip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("SUBMISSION.tsv", SUB)
        z.writestr("REPORTINGOWNER.tsv", OWN)
        z.writestr("NONDERIV_TRANS.tsv", TX)
    return zipfile.ZipFile(io.BytesIO(b.getvalue()))


def test_rows_from_zip_filters_and_shapes():
    df = bt.rows_from_zip(make_zip())
    assert len(df) == 2 and set(df["owner"]) == {"Jane", "Bob"}  # sells and Form 3 dropped
    r = df.iloc[0]
    assert r["ticker"] == "ACME" and r["is_director"] and r["is_officer"] and r["issuer_cik"] == "0000000111"


def closes(n=100, start="2024-01-01"):
    return pd.Series([100.0 + i for i in range(n)], index=pd.bdate_range(start, periods=n))


def test_entry_is_after_filing_date_no_lookahead():
    c = closes()
    out = bt.trade_returns(c, "2024-01-09", cost=0.0)
    assert out["entry_date"] == "2024-01-10"  # strictly after the filing date
    p0 = float(c["2024-01-10"])
    assert abs(out["gross_5d"] - (float(c.iloc[c.index.get_loc(pd.Timestamp("2024-01-10")) + 5]) / p0 - 1)) < 1e-12
    assert abs(bt.trade_returns(c, "2024-01-09", cost=0.025)["net_20d"] - (out["gross_20d"] - 0.025)) < 1e-12
    short = bt.trade_returns(c.iloc[:16], "2024-01-09")
    assert short["net_20d"] is None and short["net_5d"] is not None


def test_run_backtest_end_to_end_and_report():
    buys = bt.rows_from_zip(make_zip())
    buys["date"] = pd.to_datetime(buys["date"])
    buys["value"] = 50000.0
    c = closes()
    res = bt.run_backtest(buys, fetch=lambda s: c)
    assert len(res) == 1 and res.iloc[0]["public_date"] == "2024-01-09" and res.iloc[0]["entry_date"] == "2024-01-10"
    assert res.iloc[0]["excess_20d"] is not None
    rep = bt.summarise(res)
    assert "survivorship" in rep and "| 20d |" in rep
    unpriced = bt.run_backtest(buys, fetch=lambda s: pd.Series(dtype=float))
    assert not unpriced.iloc[0]["have_prices"] and "No priced clusters" in bt.summarise(unpriced)


def test_load_range_skips_missing_quarters():
    calls = []

    def dl(y, q):
        calls.append((y, q))
        return make_zip() if (y, q) == (2024, 1) else None
    df = bt.load_range(2024, 2024, dl=dl)
    assert len(calls) == 4 and len(df) == 2
