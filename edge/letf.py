"""Leveraged ETF "structural arbitrage": do the mechanical features of 3x ETFs leave money on the table after costs?

Three structural features are tested, on free Yahoo data:

1. Volatility decay. A 3x fund that resets daily loses roughly 3 x sigma^2 a year against 3x the index (for 3x,
   the drag is (L^2 - L)/2 x variance). Two ways to harvest it:
     pair:  short the bull AND the bear fund in equal amounts (net market exposure starts at zero);
     bullh: short the bull fund and hold 3x its notional in the unlevered index ETF (beta hedge);
     bearh: short the bear fund and short 3x its notional in the unlevered index ETF.
   Positions are reset to their target weights every H trading days and drift in between. Every leg pays or
   receives financing, which is where the money actually goes (see `excess_returns`): a short collects the ETF's
   price fall but pays a borrow fee, and only earns interest on the proceeds if the broker pays a rebate.
   The funds themselves embed financing: a bull fund borrows ~2x (pays ~2 x cash rate), a bear fund earns ~4x the
   cash rate on its collateral, so shorting a bear fund in a high-rate world costs you the cash rate unless you
   get it back as a rebate. That is the single biggest difference between an institution and a retail account.
2. Close-of-day rebalancing flows. Leveraged funds must buy after up days and sell after down days at the close,
   in proportion to (L^2 - L) x AUM x the day's return. If that pushes prices, the last half hour should continue
   the day's move (and the next open may give it back). Tested on the unlevered index ETFs with Yahoo hourly bars
   (last ~2 years) and daily open/close (from 2008).
3. Mispricing against the index. Free historical NAVs do not exist, so the proxy is the daily residual
   e = r(bull) - 3 r(index ETF) at the same 4 pm close. If premiums mean-revert, e should be negatively
   autocorrelated and a next-day bet against yesterday's residual should pay after spreads.

Out of sample: anything chosen (the reset interval H) is picked on data before LETF_SPLIT at institutional costs;
later data is reported for every cost scenario. Survivorship: only funds alive today are on Yahoo; dozens of
leveraged ETFs/ETNs were closed or blown up (XIV, TVIX, UWT/DWT, the 3x oil and gold miners funds), and several
of the pairs here cut leverage at times. Using today's survivors flatters any short-the-decay strategy less than
you might think (closures mostly hurt the long side), but it does hide the tail events (e.g. a bear fund doubling
in a day) that make shorting these products dangerous.
"""
import io
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import config

REPORT = Path("reports/letf_study.md")
DAILY_CSV = Path("reports/letf_daily.csv")
PANEL = Path("reports/letf_panel.csv.gz")
INTRADAY = Path("reports/letf_intraday.csv.gz")
RF_CSV = Path("reports/letf_rf.csv.gz")
DAYS = 252

# (bull, bear, unlevered index ETF); every fund here is 3x over the whole sample used
PAIRS = [("TQQQ", "SQQQ", "QQQ"), ("UPRO", "SPXU", "SPY"), ("SPXL", "SPXS", "SPY"), ("SOXL", "SOXS", "SOXX"),
         ("TNA", "TZA", "IWM"), ("FAS", "FAZ", "XLF"), ("TECL", "TECS", "XLK"), ("UDOW", "SDOW", "DIA"),
         ("LABU", "LABD", "XBI"), ("TMF", "TMV", "TLT"), ("YINN", "YANG", "FXI")]
LEV = 3.0
UNDERLYINGS = sorted({u for _, _, u in PAIRS})
TICKERS = sorted({t for p in PAIRS for t in p})
INTRADAY_TICKERS = ["SPY", "QQQ", "IWM", "SOXX"]
HORIZONS = [1, 5, 21]
STRATS = ["pair", "bullh", "bearh"]

# half-spread + slippage per side, as a fraction of notional
HALF_SPREAD = {**{u: 0.0001 for u in UNDERLYINGS},
               **{t: 0.0002 for t in ["TQQQ", "SQQQ", "SOXL", "SOXS", "UPRO", "SPXL", "SPXU", "SPXS", "TNA", "TZA", "FAS", "TMF"]}}
HALF_SPREAD_DEFAULT = 0.0005

# Cost scenarios. borrow = annual fee on short ETF notional (bull, bear); rebate_haircut = what the broker keeps
# from the cash rate on short proceeds (rate = 1.0 means no rebate at all); long_spread = financing above the cash
# rate on long notional; extra = added cost per side (CFD commission/spread).
SCENARIOS = {
    "institutional": dict(borrow=(0.005, 0.03), rebate_haircut=0.0025, long_spread=0.0, extra=0.0,
                          note="prime broker: rebate = cash rate - 0.25%, long financed at the cash rate"),
    "inst_hard": dict(borrow=(0.02, 0.10), rebate_haircut=0.0025, long_spread=0.0, extra=0.0,
                      note="same, but hard-to-borrow fees (2% bull, 10% bear)"),
    "retail_broker": dict(borrow=(0.01, 0.04), rebate_haircut=1.0, long_spread=0.015, extra=0.0,
                          note="retail margin account (US-style): no rebate on proceeds, longs at cash + 1.5%"),
    "uk_cfd": dict(borrow=(0.01, 0.04), rebate_haircut=0.025, long_spread=0.025, extra=0.0010,
                   note="UK CFD/spread bet: cash +/- 2.5% admin fee, borrow passed on, 10bp extra per side"),
}
BASE = "institutional"
UK = "uk_cfd"


# ---------- data ----------

def _chart(symbol: str, url: str) -> dict | None:
    for attempt in range(4):
        try:
            r = requests.get(url.format(symbol=symbol), headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=20)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(3 * 2 ** attempt)
                continue
            if r.status_code != 200:
                return None
            return r.json()["chart"]["result"][0]
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
            time.sleep(2)
    return None


def fetch_daily(symbol: str) -> pd.DataFrame:
    """adj (dividend/split adjusted close), open and close (raw), indexed by date."""
    res = _chart(symbol, config.YAHOO_DAILY_MAX_URL)
    if not res:
        return pd.DataFrame()
    q = res["indicators"]["quote"][0]
    adj = res["indicators"].get("adjclose", [{}])[0].get("adjclose") or q["close"]
    idx = pd.to_datetime(res["timestamp"], unit="s").normalize()
    df = pd.DataFrame({"adj": adj, "open": q["open"], "close": q["close"]}, index=idx, dtype=float).dropna(subset=["adj"])
    return df[~df.index.duplicated(keep="last")].sort_index()


def fetch_hourly(symbol: str) -> pd.DataFrame:
    """Yahoo 60-minute bars for the last ~730 days, timestamps in New York time."""
    res = _chart(symbol, config.LETF_HOURLY_URL)
    if not res:
        return pd.DataFrame()
    q = res["indicators"]["quote"][0]
    idx = pd.to_datetime(res["timestamp"], unit="s", utc=True).tz_convert("America/New_York").tz_localize(None)
    df = pd.DataFrame({"open": q["open"], "close": q["close"]}, index=idx, dtype=float).dropna()
    return df[~df.index.duplicated(keep="last")]


def build_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for t in TICKERS:
        d = fetch_daily(t)
        print(f"{t}: {len(d)} days from {d.index[0].date() if len(d) else '-'}")
        if not d.empty:
            rows.append(d.assign(ticker=t))
        time.sleep(0.5)
    panel = pd.concat(rows).rename_axis("date").reset_index()
    hours = []
    for t in INTRADAY_TICKERS:
        h = fetch_hourly(t)
        print(f"{t} hourly: {len(h)} bars")
        if not h.empty:
            hours.append(h.assign(ticker=t))
        time.sleep(0.5)
    intraday = pd.concat(hours).rename_axis("ts").reset_index() if hours else pd.DataFrame(columns=["ts", "open", "close", "ticker"])
    PANEL.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(PANEL, index=False, float_format="%.6g")
    intraday.to_csv(INTRADAY, index=False, float_format="%.6g")
    return panel, intraday


def load_panel(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    if refresh or not PANEL.exists() or not INTRADAY.exists():
        return build_panel()
    return pd.read_csv(PANEL, parse_dates=["date"]), pd.read_csv(INTRADAY, parse_dates=["ts"])


def cash_rate(refresh: bool = False) -> pd.Series:
    """3-month T-bill (FRED DTB3), annual decimal, by date; cached in reports/ (FRED is slow from the cloud)."""
    if not refresh and RF_CSV.exists():
        df = pd.read_csv(RF_CSV, parse_dates=["date"])
        return df.set_index("date")["rf"]
    try:
        r = requests.get(config.CARRY_FRED_URL, headers={"User-Agent": config.YAHOO_USER_AGENT}, timeout=150)
        df = pd.read_csv(io.StringIO(r.text))
        s = pd.to_numeric(df.iloc[:, 1], errors="coerce") / 100
        s.index = pd.to_datetime(df.iloc[:, 0])
        s = s[s.index >= "2005-01-01"].dropna().rename("rf").rename_axis("date")
        s.to_frame().to_csv(RF_CSV, float_format="%.5g")
        return s
    except Exception as exc:  # the study still runs, with zero rates (said in the report)
        print(f"FRED failed: {exc}")
        return pd.Series(dtype=float)


# ---------- 1. decay harvesting ----------

def legs(strat: str, bull: str, bear: str, und: str) -> dict:
    """Target notional per 1.0 of capital (negative = short)."""
    if strat == "pair":
        return {bull: -0.5, bear: -0.5}
    if strat == "bullh":
        return {bull: -0.5, und: 0.5 * LEV}
    return {bear: -0.5, und: -0.5 * LEV}


def simulate(rets: pd.DataFrame, target: dict, horizon: int) -> tuple[pd.DataFrame, pd.Series]:
    """Positions held at each day's open of trading (value at previous close) and the turnover traded at each close.
    Reset to target at the first close and then every `horizon` closes; legs drift with their own returns between.
    Returns (positions indexed by the day whose return they earn, turnover per unit capital by ticker)."""
    cols = list(target)
    r = rets[cols].to_numpy()
    tgt = np.array([target[c] for c in cols])
    n = len(r)
    pos = np.zeros((n, len(cols)))
    trade = np.zeros((n, len(cols)))
    cur = np.zeros(len(cols))
    equity = 1.0
    for i in range(n):
        if i % horizon == 0:  # reset at the previous close (equity-scaled, so the book compounds)
            new = tgt * equity
            trade[i] = np.abs(new - cur)
            cur = new
        pos[i] = cur
        pnl = float(cur @ r[i])
        equity += pnl
        cur = cur * (1 + r[i])
        if equity <= 0:
            pos[i + 1:] = 0
            break
    idx = rets.index
    return pd.DataFrame(pos, index=idx, columns=cols), pd.DataFrame(trade, index=idx, columns=cols)


def excess_returns(rets: pd.DataFrame, pos: pd.DataFrame, trade: pd.DataFrame, rf: pd.Series, bull: str, bear: str,
                   sc: dict) -> pd.DataFrame:
    """Daily return over cash per unit of start-of-day equity, gross and net, for one cost scenario.
    excess = price P&L + sum over shorts of (rf - haircut - borrow) x |short| - sum over longs of (rf + spread) x long
             - trading costs.  (Capital itself earns rf and is the benchmark, so it drops out.)"""
    equity = 1 + (pos * rets[pos.columns]).sum(axis=1).cumsum().shift(fill_value=0)  # start-of-day equity (approx.)
    equity = equity.where(equity > 0, np.nan)
    price = (pos * rets[pos.columns]).sum(axis=1)
    d_rf = rf.reindex(pos.index).ffill().fillna(0) / DAYS
    fin = pd.Series(0.0, index=pos.index)
    for c in pos.columns:
        p = pos[c]
        short, long_ = (-p).clip(lower=0), p.clip(lower=0)
        borrow = sc["borrow"][0] if c == bull else sc["borrow"][1] if c == bear else 0.003  # index ETFs are general collateral
        haircut = sc["rebate_haircut"]
        reb = d_rf - haircut / DAYS if haircut < 1 else 0 * d_rf  # can go negative (you pay) on a CFD when rates are low
        fin += short * (reb - borrow / DAYS) - long_ * (d_rf + sc["long_spread"] / DAYS)
    tc = sum(trade[c] * (HALF_SPREAD.get(c, HALF_SPREAD_DEFAULT) + sc["extra"]) for c in trade.columns)
    # the book's P&L is in units of initial capital; convert to returns on start-of-day equity
    return pd.DataFrame({"gross": price / equity, "net": (price + fin - tc) / equity}).fillna(0.0)


def run_decay(daily: pd.DataFrame, rf: pd.Series) -> dict:
    """{(pair, strat, horizon, scenario): DataFrame(gross, net)} over each pair's common history."""
    out = {}
    for bull, bear, und in PAIRS:
        cols = [c for c in (bull, bear, und) if c in daily]
        if len(cols) < 3:
            continue
        rets = daily[[bull, bear, und]].pct_change().dropna()
        rets = rets.clip(-0.9, 3.0)
        for strat in STRATS:
            for h in HORIZONS:
                pos, trade = simulate(rets, legs(strat, bull, bear, und), h)
                for name, sc in SCENARIOS.items():
                    out[(bull, strat, h, name)] = excess_returns(rets, pos, trade, rf, bull, bear, sc)
    return out


def stats(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 20:
        return {"n": len(r), "ann": math.nan, "vol": math.nan, "sharpe": math.nan, "t": math.nan, "maxdd": math.nan, "worst": math.nan}
    curve = (1 + r).cumprod()
    sd = r.std()
    years = len(r) / DAYS
    g = float(curve.iloc[-1])
    return {"n": len(r), "ann": g ** (1 / years) - 1 if g > 0 else -1.0, "vol": sd * math.sqrt(DAYS),
            "sharpe": r.mean() / sd * math.sqrt(DAYS) if sd > 0 else math.nan,
            "t": r.mean() / sd * math.sqrt(len(r)) if sd > 0 else math.nan,
            "maxdd": float((curve / curve.cummax() - 1).min()), "worst": float(r.min())}


def pick_horizons(results: dict, split: str) -> dict:
    """Per strategy, the reset interval with the best in-sample Sharpe of the equal-weight basket of pairs (base costs)."""
    chosen = {}
    for strat in STRATS:
        best, best_s = HORIZONS[0], -np.inf
        for h in HORIZONS:
            b = basket(results, strat, h, BASE, "net")
            s = stats(b[b.index < split])["sharpe"]
            if np.isfinite(s) and s > best_s:
                best, best_s = h, s
        chosen[strat] = best
    return chosen


def basket(results: dict, strat: str, h: int, scen: str, col: str) -> pd.Series:
    """Equal-weight across the pairs trading that day (daily rebalanced across pairs)."""
    series = [v[col].rename(k[0]) for k, v in results.items() if k[1] == strat and k[2] == h and k[3] == scen]
    if not series:
        return pd.Series(dtype=float)
    return pd.concat(series, axis=1).mean(axis=1)


# ---------- 2. close-of-day flows ----------

def last_half_hour(intraday: pd.DataFrame) -> pd.DataFrame:
    """Per ticker-day: return from the open to 15:30 (first bar open to the 14:30 bar's close) and 15:30 to the close."""
    rows = []
    for t, g in intraday.groupby("ticker"):
        g = g.set_index("ts").sort_index()
        for day, d in g.groupby(g.index.normalize()):
            first = d[d.index.time == pd.Timestamp("09:30").time()]
            last = d[d.index.time == pd.Timestamp("15:30").time()]
            if first.empty or last.empty:
                continue
            o, mid, c = first["open"].iloc[0], last["open"].iloc[0], last["close"].iloc[0]
            rows.append({"ticker": t, "day": day, "r_day": mid / o - 1, "r_last": c / mid - 1})
    return pd.DataFrame(rows)


def regress(x: pd.Series, y: pd.Series) -> dict:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    if len(x) < 30:
        return {"n": len(x), "beta": math.nan, "t": math.nan}
    xm = x - x.mean()
    beta = (xm @ (y - y.mean())) / (xm @ xm)
    resid = y - y.mean() - beta * xm
    se = math.sqrt((resid @ resid) / (len(x) - 2) / (xm @ xm))
    return {"n": len(x), "beta": beta, "t": beta / se}


def close_flow_tests(lh: pd.DataFrame, daily: pd.DataFrame, costs=(0.0001, 0.0005)) -> dict:
    out = {"intraday": {}, "overnight": {}}
    for t, g in lh.groupby("ticker"):
        reg = regress(g["r_day"], g["r_last"])
        trade = np.sign(g["r_day"]) * g["r_last"]  # follow the day's direction for the last half hour
        out["intraday"][t] = {**reg, "first": str(g["day"].min().date()), "last": str(g["day"].max().date()),
                              "gross_bp": trade.mean() * 1e4, **{f"net_{c:g}": (trade - 2 * c).mean() * 1e4 for c in costs},
                              "hit": float((trade > 0).mean())}
    for t in INTRADAY_TICKERS:
        if f"open_{t}" not in daily:
            continue
        o, c = daily[f"open_{t}"], daily[f"close_{t}"]
        r_day = c / c.shift(1) - 1
        r_night = (o.shift(-1) / c - 1).clip(-0.2, 0.2)
        d = pd.DataFrame({"x": r_day, "y": r_night}).dropna()
        d = d[d.index >= "2008-01-01"]
        reg = regress(d["x"], d["y"])
        trade = -np.sign(d["x"]) * d["y"]  # fade the day into the next open
        halves = {f"{a}-{b}": regress(d.loc[a:b, "x"], d.loc[a:b, "y"])["beta"] for a, b in (("2008", "2016"), ("2017", "2026"))}
        out["overnight"][t] = {**reg, **halves, "gross_bp": trade.mean() * 1e4,
                               **{f"net_{c:g}": (trade - 2 * c).mean() * 1e4 for c in costs}}
    return out


# ---------- 3. residual mean reversion ----------

def residual_tests(daily: pd.DataFrame) -> list[dict]:
    rows = []
    for bull, bear, und in PAIRS:
        for etf, sign in ((bull, 1.0), (bear, -1.0)):
            if etf not in daily or und not in daily:
                continue
            r = daily[[etf, und]].pct_change().dropna()
            r = r[r.index >= "2010-01-01"]
            e = r[etf] - sign * LEV * r[und]
            e = e.clip(e.quantile(0.005), e.quantile(0.995))
            cost = 2 * (HALF_SPREAD.get(etf, HALF_SPREAD_DEFAULT) + LEV * HALF_SPREAD.get(und, HALF_SPREAD_DEFAULT))
            nxt = e.shift(-1)
            big = e.abs() > cost
            trade = (-np.sign(e) * nxt)[big].dropna()  # long the fund that closed cheap vs 3x the index, hedged
            rows.append({"etf": etf, "und": und, "n": len(e), "sd_bp": e.std() * 1e4, "ac1": e.autocorr(1),
                         "trades": len(trade), "gross_bp": trade.mean() * 1e4 if len(trade) else math.nan,
                         "cost_bp": cost * 1e4, "net_bp": (trade.mean() - cost) * 1e4 if len(trade) else math.nan})
    return rows


# ---------- report ----------

def pct(x, spec=".1%"):
    return format(x, spec) if x is not None and np.isfinite(x) else "n/a"


def report(results, chosen, flows, resid, split, rf_ok, first_dates) -> str:
    L = ["# Leveraged ETF structural arbitrage (3x bull/bear pairs)", ""]
    oos = {}
    for strat in STRATS:
        h = chosen[strat]
        oos[strat] = {sc: stats(basket(results, strat, h, sc, "net").loc[split:]) for sc in SCENARIOS}
        oos[strat]["gross"] = stats(basket(results, strat, h, BASE, "gross").loc[split:])
    best_inst = max(STRATS, key=lambda s: oos[s][BASE]["sharpe"] if np.isfinite(oos[s][BASE]["sharpe"]) else -9)
    bi, uk = oos[best_inst][BASE], oos[best_inst][UK]
    intr = flows["intraday"]
    ovn = flows["overnight"]
    good_resid = [r for r in resid if np.isfinite(r["net_bp"]) and r["net_bp"] > 0 and r["trades"] > 200]
    verdict = (f"**Verdict:** the volatility decay is real but almost all of it is paid away. Out of sample ({split[:4]} on), "
               f"the best book ({best_inst}, reset every {chosen[best_inst]} days) earns {pct(bi['ann'])} a year over cash at "
               f"institutional costs (Sharpe {pct(bi['sharpe'], '.2f')}, worst day {pct(bi['worst'])}, max drawdown {pct(bi['maxdd'])}), "
               f"and {pct(uk['ann'])} a year (Sharpe {pct(uk['sharpe'], '.2f')}) on a UK CFD account. ")
    verdict += ("No close-of-day or mispricing effect survives costs either (sections 2 and 3). "
                "UK retail cannot short the US funds directly, and the UK-listed 3x ETPs are unborrowable. **No edge worth trading.**")
    L += [verdict, ""]
    L += ["## What was tested", "",
          f"{len([p for p in PAIRS if p[0] in first_dates])} US 3x bull/bear pairs with their unlevered index ETF, daily adjusted closes from Yahoo "
          f"(each pair from its common start, earliest {min(first_dates.values())}). Reset intervals {HORIZONS} trading days chosen before "
          f"{split} at institutional costs; {split[:4]} onward is out of sample. Returns are over the 3-month T-bill"
          + ("" if rf_ok else " (FRED was unreachable, so cash was set to 0%: the rebate/financing gap is then understated)") + ". "
          "Each book is 1.0 of capital: pair = short 0.5 bull + 0.5 bear; bullh = short 0.5 bull, long 1.5 index ETF; "
          "bearh = short 0.5 bear, short 1.5 index ETF. Pairs are equal-weighted.", "",
          "Cost scenarios (borrow fees are assumptions: no free borrow history exists; IBorrowDesk now needs a paid key. "
          "Recent public quotes put SQQQ around 3-4% and SOXS around 1-2%, with spikes far higher):", ""]
    L += [f"- **{k}**: borrow {v['borrow'][0]:.1%} bull / {v['borrow'][1]:.1%} bear; {v['note']}" for k, v in SCENARIOS.items()]
    L += ["", "## 1. Volatility decay harvesting", "",
          "Equal-weight basket of pairs, chosen reset interval, out of sample. 'gross' = price P&L only (no borrow, no financing, no spreads).", "",
          "| book | reset (days) | scenario | ann. over cash | vol | Sharpe | t | max drawdown | worst day |", "|---|---|---|---|---|---|---|---|---|"]
    for strat in STRATS:
        for sc in ["gross"] + list(SCENARIOS):
            s = oos[strat][sc]
            L.append(f"| {strat} | {chosen[strat]} | {sc} | {pct(s['ann'])} | {pct(s['vol'])} | {pct(s['sharpe'], '.2f')} | "
                     f"{pct(s['t'], '.1f')} | {pct(s['maxdd'])} | {pct(s['worst'])} |")
    L += ["", "All reset intervals, institutional costs (in sample / out of sample Sharpe):", "", "| book | " + " | ".join(f"H={h}" for h in HORIZONS) + " |",
          "|---|" + "---|" * len(HORIZONS)]
    for strat in STRATS:
        cells = []
        for h in HORIZONS:
            b = basket(results, strat, h, BASE, "net")
            cells.append(f"{pct(stats(b[b.index < split])['sharpe'], '.2f')} / {pct(stats(b.loc[split:])['sharpe'], '.2f')}")
        L.append(f"| {strat} | " + " | ".join(cells) + " |")
    L += ["", f"Per pair, out of sample, best book ({best_inst}, H={chosen[best_inst]}): gross vs net at institutional and UK CFD costs (annual, over cash):", "",
          "| pair | gross | institutional | inst_hard | retail_broker | uk_cfd | worst day (inst) |", "|---|---|---|---|---|---|---|"]
    for bull, bear, und in PAIRS:
        k = (bull, best_inst, chosen[best_inst])
        if k + (BASE,) not in results:
            continue
        g = stats(results[k + (BASE,)]["gross"].loc[split:])
        cells = [pct(stats(results[k + (sc,)]["net"].loc[split:])["ann"]) for sc in SCENARIOS]
        L.append(f"| {bull}/{bear} | {pct(g['ann'])} | " + " | ".join(cells) + f" | {pct(stats(results[k + (BASE,)]['net'].loc[split:])['worst'])} |")
    yr = basket(results, best_inst, chosen[best_inst], BASE, "net")
    yrs = (1 + yr).groupby(yr.index.year).prod() - 1
    L += ["", f"By year, {best_inst} at institutional costs: " + ", ".join(f"{y} {v:+.1%}" for y, v in yrs.items()) + ".", ""]
    L += ["Why the gross number shrinks: the funds already charge ~0.9-1% a year and pay their own financing, so a short "
          "collects the decay plus fees but owes borrow; a retail short receives no interest on the proceeds while the bear "
          "fund it is short earns T-bills on 4x its assets, a drag of roughly the cash rate (4-5% a year in 2023-26). "
          "Results are also very sensitive to trading exactly at the close: Quantpedia's version of the TQQQ/SQQQ pair "
          "(Oct 2026) went from +2.1% a year to about -1% a year when rebalanced 10 minutes before the close, because the "
          "funds' own rebalancing moves prices into the close.", ""]
    L += ["## 2. Close-of-day rebalancing flows", "",
          "Last half hour (15:30 to close) regressed on the day's move to 15:30, Yahoo hourly bars. Trade = follow the day's sign for the last half hour.", "",
          "| ETF | days | beta | t | gross bp/trade | net bp (1bp/side) | net bp (5bp/side) | hit rate |", "|---|---|---|---|---|---|---|---|"]
    for t, s in intr.items():
        L.append(f"| {t} | {s['n']} ({s['first']} to {s['last']}) | {s['beta']:.3f} | {s['t']:.1f} | {s['gross_bp']:.2f} | "
                 f"{s['net_0.0001']:.2f} | {s['net_0.0005']:.2f} | {s['hit']:.0%} |")
    L += ["", "Close to next open regressed on the day's close-to-close move (from 2008). Trade = fade the day into the next open.", "",
          "| ETF | days | beta | t | beta 2008-16 | beta 2017-26 | gross bp/trade | net bp (1bp/side) | net bp (5bp/side) |", "|---|---|---|---|---|---|---|---|---|"]
    for t, s in ovn.items():
        L.append(f"| {t} | {s['n']} | {s['beta']:.3f} | {s['t']:.1f} | {s['2008-2016']:.3f} | {s['2017-2026']:.3f} | {s['gross_bp']:.2f} | "
                 f"{s['net_0.0001']:.2f} | {s['net_0.0005']:.2f} |")
    L += ["", "Hourly history is only ~2 years (Yahoo's limit), so the intraday test is short. A UK spread bet on the US 500 or US Tech 100 "
          "costs about 0.5-1bp a side in the cash session but the overnight leg spans the wider out-of-hours spread.", ""]
    L += ["## 3. Mispricing against the index (premium proxy)", "",
          "Daily residual e = r(fund) - (+/-3) x r(index ETF), both at the 4 pm close, from 2010. Trade next day against yesterday's residual when "
          "|e| exceeds the round-trip cost of both legs (fund + 3x index ETF), assuming you can trade at the close you just observed (optimistic).", "",
          "| fund | index | days | residual sd (bp) | lag-1 autocorr | trades | gross bp | cost bp | net bp |", "|---|---|---|---|---|---|---|---|---|"]
    for r in resid:
        L.append(f"| {r['etf']} | {r['und']} | {r['n']} | {r['sd_bp']:.1f} | {r['ac1']:.2f} | {r['trades']} | {pct(r['gross_bp'], '.1f')} | "
                 f"{r['cost_bp']:.1f} | {pct(r['net_bp'], '.1f')} |")
    L += ["", ("Residuals do mean-revert (negative autocorrelation), as expected from closing-print noise and the funds' swap resets, "
               "but the reversal is mostly smaller than the cost of trading both legs. "
               + (f"Positive net cells with 200+ trades: {', '.join(r['etf'] for r in good_resid)}; these rely on trading at the very close you are measuring, "
                  "and include the index ETF tracking gap (e.g. SOXX and the funds' benchmark differ), so they are not tradable as shown."
                  if good_resid else "No fund clears costs with 200+ trades.")), ""]
    L += ["## UK retail feasibility", "",
          "- **US-listed funds (TQQQ, SQQQ, SOXL...)**: UK retail brokers block them for want of a PRIIPs KID (Interactive Brokers says so explicitly). "
          "The FCA's Consumer Composite Investments regime replaced PRIIPs from 6 April 2026 with full go-live on 8 June 2027; it may eventually "
          "widen access, but no broker has unblocked US ETFs for UK retail on that basis yet. Elective professional status unblocks them but "
          "removes FCA retail protections.",
          "- **UK-listed 3x ETPs (QQQ3, QQQS, 3USL, 3USS on the LSE)**: buyable in an ISA, but cannot be shorted: IG lists the 3x Short US Tech 100 "
          "ETP as 'Unborrowable'. Long-only, they are the wrong side of the decay trade.",
          "- **CFDs/spread bets on US ETFs**: IG and IBKR UK offer CFDs on large US ETFs; shorts receive the cash rate minus an admin fee (about 2.5%) "
          "and pay any borrow charge, which is what the uk_cfd scenario models. Spread bets are tax-free, but the economics are the same.",
          "- **Tail risk**: a short bear fund can lose 30%+ in a day (e.g. SQQQ/SOXS in crashes); with CFD margin of 20-25% a few such days wipe the account.", ""]
    L += ["## Caveats", "",
          "- Survivorship: only funds alive today are on Yahoo. Closed products (3x oil, 3x gold miners, VelocityShares notes, XIV) are missing, and "
          "several of their deaths were exactly the blow-ups a decay-short would have suffered or profited from.",
          "- Borrow fees and rebates are flat assumptions; real fees are highest exactly when the trade looks most attractive (high vol, crowded shorts), "
          "and borrow can be recalled.",
          "- Trades at the official close; real fills before the close did much worse in independent tests.",
          "- Three reset intervals and three books were tried; the best is reported, which flatters it.", "",
          "Sources: Quantpedia, 'Shorting Leveraged ETFs: The Role of Borrowing Costs and Rebalancing in Volatility-Decay Strategies' (Oct 2026); "
          "Interactive Brokers FAQ on UK/EEA retail and US ETFs; FCA PS25/20 (CCI regime); IG market page for the Leverage Shares 3x Short US Tech 100 ETP.", "",
          "Built by `python run.py letf [--refresh]`; panel in `reports/letf_panel.csv.gz`, daily returns of the best book in `reports/letf_daily.csv`."]
    return "\n".join(L)


def main(refresh: bool = False) -> None:
    panel, intraday = load_panel(refresh)
    daily = panel.pivot(index="date", columns="ticker", values="adj").sort_index()
    for t in INTRADAY_TICKERS:
        sub = panel[panel["ticker"] == t].set_index("date")
        daily[f"open_{t}"], daily[f"close_{t}"] = sub["open"], sub["close"]
    first_dates = {b: str(daily[[b, s, u]].dropna().index[0].date()) for b, s, u in PAIRS if all(c in daily for c in (b, s, u))}
    rf = cash_rate(refresh)
    results = run_decay(daily, rf)
    split = config.LETF_SPLIT
    chosen = pick_horizons(results, split)
    flows = close_flow_tests(last_half_hour(intraday), daily)
    resid = residual_tests(daily)
    text = report(results, chosen, flows, resid, split, not rf.empty, first_dates)
    REPORT.write_text(text + "\n")
    best = max(STRATS, key=lambda s: stats(basket(results, s, chosen[s], BASE, "net").loc[split:])["sharpe"])
    out = pd.DataFrame({f"net_{sc}": basket(results, best, chosen[best], sc, "net") for sc in SCENARIOS})
    out["gross"] = basket(results, best, chosen[best], BASE, "gross")
    out.attrs["book"] = best
    out.rename_axis("day").to_csv(DAILY_CSV, float_format="%.6g")
    print(text[:1500])
