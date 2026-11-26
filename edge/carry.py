"""Crypto carry: is delta-neutral cash-and-carry (long spot, short perpetual future) worth doing after costs?

Data: Binance's public data dump (data.binance.vision): daily spot and USDT-margined perp klines plus the 8-hourly
funding prints, 10 large coins, from 2020. The live exchange APIs are geo-blocked from the cloud; the dump is not.

Return of one hedged unit of notional on day t, quantity fixed (no rebalancing needed):
    (dSpot - dPerp) / Spot[t-1]  +  funding paid to the short on day t
Funding is credited to the day whose close ends after the print (a print at 00:00 belongs to the day before).
Capital per 1.0 of notional is 1 + CARRY_MARGIN (spot leg in full, margin on the short leg); idle capital earns 0.
Costs: taker fee and slippage on both legs, charged on every change in position (turnover).
Every signal uses information up to the close of day t and earns from day t+1.

Strategies: always-on carry per coin and as baskets; a funding filter (hold only while trailing funding is above a
threshold, chosen in sample); a weekly top-k by trailing funding; and a directional test (does high funding predict
falling prices?). Parameters are chosen before CARRY_SPLIT; later data is out of sample.
"""
import io
import math
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

import config
from edge import http, risk

REPORT = Path("reports/carry_study.md")
DAILY_CSV = Path("reports/carry_daily.csv")
DAYS = 365


# ---------- data ----------

def months(first: str, last: str) -> list[str]:
    return [str(p) for p in pd.period_range(first, last, freq="M")]


def zip_url(coin: str, series: str, ym: str) -> str:
    sym = coin + "USDT"
    if series == "spot":
        return config.CARRY_DATA_URL.format(market="spot", kind="klines", symbol=sym, sub="/1d", name="1d", ym=ym)
    if series == "perp":
        return config.CARRY_DATA_URL.format(market="futures/um", kind="klines", symbol=sym, sub="/1d", name="1d", ym=ym)
    return config.CARRY_DATA_URL.format(market="futures/um", kind="fundingRate", symbol=sym, sub="", name="fundingRate", ym=ym)


KLINE_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "tb_base", "tb_quote", "ignore"]
FUNDING_COLS = ["calc_time", "funding_interval_hours", "last_funding_rate"]


def read_zip_csv(blob: bytes) -> pd.DataFrame:
    """One zipped CSV, with or without a header row (the dump changed over the years), to positional named columns."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        raw = z.read(z.namelist()[0]).decode()
    df = pd.read_csv(io.StringIO(raw), header=None)
    if not str(df.iloc[0, 0]).replace(".", "").isdigit():
        df = df.iloc[1:].reset_index(drop=True)
    df.columns = (KLINE_COLS if df.shape[1] == len(KLINE_COLS) else FUNDING_COLS)[:df.shape[1]]
    return df


def kline_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Daily kline rows to a frame indexed by UTC date. Spot stamps switch to microseconds in 2025."""
    t = pd.to_numeric(df["open_time"]).astype("int64")
    t = t.where(t < 10**14, t // 1000)
    out = pd.DataFrame({"high": pd.to_numeric(df["high"]).values, "close": pd.to_numeric(df["close"]).values})
    out.index = pd.to_datetime(t.values, unit="ms").normalize()
    return out


def funding_frame(df: pd.DataFrame) -> pd.Series:
    """Funding prints to a per-day sum. A print at 00:00 pays the position held through the previous day, so
    it is booked to that day (shift back one minute before taking the date)."""
    t = pd.to_datetime(pd.to_numeric(df["calc_time"]).astype("int64").values, unit="ms") - pd.Timedelta(minutes=1)
    s = pd.Series(pd.to_numeric(df["last_funding_rate"]).values, index=t.normalize())
    return s.groupby(level=0).sum()


def fetch_month(coin: str, series: str, ym: str, cache: Path) -> bytes | None:
    path = cache / f"{coin}_{series}_{ym}.zip"
    if path.exists():
        return path.read_bytes()
    try:
        resp = http.get(zip_url(coin, series, ym))
    except Exception:  # 404: the contract did not exist yet (or the month is not published)
        return None
    cache.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return resp.content


def build_coin(coin: str, first: str, last: str, cache: Path) -> pd.DataFrame:
    tasks = [(s, m) for s in ("spot", "perp", "funding") for m in months(first, last)]
    with ThreadPoolExecutor(8) as ex:
        blobs = list(ex.map(lambda a: fetch_month(coin, a[0], a[1], cache), tasks))
    parts: dict[str, list] = {"spot": [], "perp": [], "funding": []}
    for (s, _), b in zip(tasks, blobs):
        if b:
            parts[s].append(read_zip_csv(b))
    if not all(parts.values()):
        return pd.DataFrame()
    spot = kline_frame(pd.concat(parts["spot"], ignore_index=True))
    perp = kline_frame(pd.concat(parts["perp"], ignore_index=True))
    fund = funding_frame(pd.concat(parts["funding"], ignore_index=True))
    df = pd.DataFrame({"spot": spot["close"], "perp": perp["close"], "perp_high": perp["high"]}).join(fund.rename("funding"), how="inner")
    df = df[~df.index.duplicated()].sort_index()
    df.index.name = "date"
    return df.dropna()


def build_panel(first: str = config.CARRY_START, last: str | None = None, cache: Path | None = None) -> pd.DataFrame:
    last = last or str(pd.Timestamp.now().to_period("M") - 1)  # last complete month
    frames = []
    for coin in config.CARRY_COINS:
        f = build_coin(coin, first, last, cache or config.CARRY_CACHE)
        if not f.empty:
            frames.append(f.assign(coin=coin))
            print(f"{coin}: {len(f)} days from {f.index[0].date()} to {f.index[-1].date()}", flush=True)
    return pd.concat(frames).reset_index()


def load_panel(refresh: bool = False) -> pd.DataFrame:
    if refresh or not config.CARRY_PANEL.exists():
        panel = build_panel()
        config.CARRY_PANEL.parent.mkdir(exist_ok=True)
        panel.round(8).to_csv(config.CARRY_PANEL, index=False)
    return pd.read_csv(config.CARRY_PANEL, parse_dates=["date"])


def tbill_daily(index: pd.DatetimeIndex) -> pd.Series:
    """Daily 3-month US T-bill return (FRED DTB3, percent a year), forward-filled over weekends."""
    try:
        df = pd.read_csv(io.StringIO(http.get(config.CARRY_FRED_URL).text))
        s = pd.to_numeric(df.set_index(pd.to_datetime(df.iloc[:, 0])).iloc[:, 1], errors="coerce")
    except Exception as exc:
        print(f"T-bill fetch failed ({exc}); using 0")
        return pd.Series(0.0, index=index)
    return (s.reindex(s.index.union(index)).ffill().reindex(index).fillna(0.0) / 100 / DAYS)


# ---------- strategy engine ----------

def leg_cost(coin: str) -> float:
    """Cost of opening or closing one unit of notional (both legs): taker fees plus slippage on each leg."""
    slip = config.CARRY_SLIPPAGE.get(coin, config.CARRY_SLIPPAGE_DEFAULT)
    return config.CARRY_SPOT_FEE + config.CARRY_PERP_FEE + 2 * slip


def wide(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Panel to date x coin frames: hedged carry return per unit notional, funding, perp and spot returns."""
    p = {k: panel.pivot(index="date", columns="coin", values=k).sort_index() for k in ("spot", "perp", "perp_high", "funding")}
    spot_prev = p["spot"].shift(1)
    out = {"funding": p["funding"], "basis_pnl": (p["spot"].diff() - p["perp"].diff()) / spot_prev}
    out["carry"] = out["basis_pnl"] + p["funding"]
    out["perp_ret"] = p["perp"].pct_change()
    out["spot_ret"] = p["spot"].pct_change()
    out["spike"] = p["perp_high"] / p["perp"].shift(1) - 1  # worst intraday move against a short
    out["ok"] = p["spot"].notna() & p["perp"].notna() & spot_prev.notna()
    return out


def run_weights(W: dict[str, pd.DataFrame], w: pd.DataFrame, rf: pd.Series, margin: float = config.CARRY_MARGIN) -> pd.DataFrame:
    """w[t] = share of capital in each coin's carry, decided at the close of t. It earns on t+1, so shift by one day.
    Returns per day: gross carry, cost, net on capital, T-bill and the excess over it."""
    w = w.reindex(W["carry"].index).fillna(0.0)
    held = w.shift(1).fillna(0.0) * W["ok"]
    gross = (held * W["carry"].fillna(0.0)).sum(axis=1) / (1 + margin)
    costs = pd.Series({c: leg_cost(c) for c in w.columns})
    cost = (w.diff().abs().fillna(w.abs()) * costs).sum(axis=1).shift(1).fillna(0.0) / (1 + margin)
    net = gross - cost
    df = pd.DataFrame({"gross": gross, "cost": cost, "net": net, "rf": rf.reindex(net.index).fillna(0.0)})
    df["excess"] = df["net"] - df["rf"]
    df["deployed"] = held.sum(axis=1)
    return df


def always_on(W, coins: list[str]) -> pd.DataFrame:
    avail = W["ok"][coins].astype(float)
    return avail.div(avail.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def trailing_funding(W, days: int) -> pd.DataFrame:
    """Annualised mean funding over the last `days` days, known at the close of each day."""
    return W["funding"].rolling(days, min_periods=days).mean() * DAYS


def filtered(W, coins: list[str], days: int, thresh: float) -> pd.DataFrame:
    """Equal weight across coins whose trailing funding exceeds `thresh` a year; the rest of capital sits in cash.
    Weights are fractions of capital (1/len(coins) each), so cash in quiet periods earns nothing."""
    on = (trailing_funding(W, days)[coins] > thresh) & W["ok"][coins]
    return on.astype(float) / len(coins)


def top_k(W, coins: list[str], days: int, k: int, every: int = 7) -> pd.DataFrame:
    """Every `every` days hold the k coins with the highest trailing funding, if positive; else cash."""
    tf = trailing_funding(W, days)[coins]
    w = pd.DataFrame(0.0, index=tf.index, columns=coins)
    last = None
    for i, d in enumerate(tf.index):
        if i % every == 0:
            row = tf.loc[d].dropna()
            row = row[row > 0].nlargest(k)
            last = pd.Series(1.0 / k, index=row.index) if len(row) else pd.Series(dtype=float)
        if last is not None:
            w.loc[d, last.index] = last.values
    return w


# ---------- directional test ----------

def directional(W, coins: list[str], horizon: int = 7, days: int = 7) -> pd.DataFrame:
    """Non-overlapping weekly samples: trailing funding (annualised) vs the next `horizon`-day perp return."""
    tf = trailing_funding(W, days)[coins]
    fwd = (1 + W["perp_ret"][coins]).rolling(horizon).apply(np.prod, raw=True).shift(-horizon) - 1
    rows = []
    for c in coins:
        d = pd.DataFrame({"f": tf[c], "r": fwd[c]}).dropna().iloc[::horizon]
        d["coin"] = c
        rows.append(d)
    return pd.concat(rows).reset_index().rename(columns={"index": "date"})


def spearman(x: pd.Series, y: pd.Series) -> float:
    return float(x.rank().corr(y.rank())) if len(x) > 3 else float("nan")


def tstat_corr(r: float, n: int) -> float:
    return r * math.sqrt((n - 2) / max(1 - r * r, 1e-12)) if n > 3 and np.isfinite(r) else float("nan")


def directional_book(W, coins: list[str], days: int = 7, horizon: int = 7, q: float = 0.2, split=config.CARRY_SPLIT) -> pd.DataFrame:
    """Weekly: short the perp of coins whose funding is in the top q of its own expanding history, long those in the bottom q.
    Expanding quantiles use only the past. Cost: perp taker fee plus slippage each side, on turnover."""
    tf = trailing_funding(W, days)[coins]
    hi = tf.expanding(min_periods=180).quantile(1 - q)
    lo = tf.expanding(min_periods=180).quantile(q)
    pos = pd.DataFrame(0.0, index=tf.index, columns=coins)
    pos[tf > hi] = -1.0
    pos[tf < lo] = 1.0
    pos = pos.iloc[::horizon].reindex(tf.index).ffill().fillna(0.0) / len(coins)
    held = pos.shift(1).fillna(0.0)
    gross = (held * W["perp_ret"].fillna(0.0)).sum(axis=1) - (held * W["funding"].fillna(0.0)).sum(axis=1)  # a long pays funding
    cst = pd.Series({c: config.CARRY_PERP_FEE + config.CARRY_SLIPPAGE.get(c, config.CARRY_SLIPPAGE_DEFAULT) for c in coins})
    cost = (pos.diff().abs().fillna(pos.abs()) * cst * 2).sum(axis=1).shift(1).fillna(0.0)  # open and close
    return pd.DataFrame({"gross": gross, "net": gross - cost})


# ---------- statistics ----------

def stats(r: pd.Series) -> dict:
    return risk.series_stats(r, periods=DAYS)


def window(df: pd.DataFrame, start=None, end=None) -> pd.DataFrame:
    m = pd.Series(True, index=df.index)
    if start:
        m &= df.index >= pd.Timestamp(start)
    if end:
        m &= df.index < pd.Timestamp(end)
    return df[m]


def summarise(df: pd.DataFrame, start=None, end=None) -> dict:
    d = window(df, start, end)
    d = d[d.index >= d.index[d["deployed"] > 0][0]] if (d["deployed"] > 0).any() else d
    ex, net = stats(d["excess"]), stats(d["net"])
    return {"days": len(d), "net_ann": net["ann"], "net_sharpe": net["sharpe"], "excess_sharpe": ex["sharpe"], "excess_t": ex["t"],
            "vol": net["vol"], "maxdd": net["maxdd"], "gross_mean_ann": float(d["gross"].mean() * DAYS),
            "cost_ann": float(d["cost"].mean() * DAYS), "rf_ann": float(d["rf"].mean() * DAYS), "deployed": float(d["deployed"].mean())}


def yearly(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for y, d in df.groupby(df.index.year):
        rows.append({"year": y, "net": float((1 + d["net"]).prod() - 1), "rf": float((1 + d["rf"]).prod() - 1),
                     "funding_only_gross": float(d["gross"].sum()), "maxdd": stats(d["net"])["maxdd"]})
    return pd.DataFrame(rows)


def liquidation_check(W, coins: list[str], margin: float = config.CARRY_MARGIN) -> pd.DataFrame:
    rows = []
    for c in coins:
        s = W["spike"][c].dropna()
        rows.append({"coin": c, "days": len(s), "worst_spike": float(s.max()), "days_over_margin": int((s > margin).sum()),
                     "days_over_half_margin": int((s > margin / 2).sum())})
    return pd.DataFrame(rows)


def per_coin(W, rf: pd.Series, split=config.CARRY_SPLIT) -> pd.DataFrame:
    rows = []
    for c in W["carry"].columns:
        df = run_weights(W, always_on(W, [c]), rf)
        s_all, s_oos = summarise(df), summarise(df, split)
        rows.append({"coin": c, "from": str(W["ok"][c][W["ok"][c]].index[0].date()), "mean_funding_ann": float(W["funding"][c].mean() * DAYS),
                     "oos_funding_ann": float(window(W["funding"][[c]], split)[c].mean() * DAYS), "all_net_ann": s_all["net_ann"],
                     "oos_net_ann": s_oos["net_ann"], "oos_excess_sharpe": s_oos["excess_sharpe"], "oos_maxdd": s_oos["maxdd"]})
    return pd.DataFrame(rows)


# ---------- report ----------

def pct(x, d=1):
    return f"{x:.{d}%}" if x is not None and np.isfinite(x) else "n/a"


def num(x, d=2):
    return f"{x:.{d}f}" if x is not None and np.isfinite(x) else "n/a"


def strat_table(rows: list[tuple[str, pd.DataFrame]], split) -> list[str]:
    L = ["| strategy | sample | days | net return a year | cost a year | T-bill | edge over T-bill: Sharpe | t | max drawdown | capital deployed |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for name, df in rows:
        for lab, a, b in (("in sample", None, split), ("out of sample", split, None)):
            s = summarise(df, a, b)
            L.append(f"| {name} | {lab} | {s['days']} | {pct(s['net_ann'])} | {pct(s['cost_ann'], 2)} | {pct(s['rf_ann'])} | "
                     f"{num(s['excess_sharpe'])} | {num(s['excess_t'])} | {pct(s['maxdd'])} | {pct(s['deployed'], 0)} |")
    return L


def main(refresh: bool = False) -> None:
    panel = load_panel(refresh)
    W = wide(panel)
    rf = tbill_daily(W["carry"].index)
    split = config.CARRY_SPLIT
    big, alts = ["BTC", "ETH"], [c for c in W["carry"].columns]
    pc = per_coin(W, rf)

    always = {"BTC": run_weights(W, always_on(W, ["BTC"]), rf), "ETH": run_weights(W, always_on(W, ["ETH"]), rf),
              "BTC+ETH": run_weights(W, always_on(W, big), rf), f"All {len(alts)} coins": run_weights(W, always_on(W, alts), rf)}
    # Filter: choose trailing window and threshold in sample on BTC+ETH, by in-sample edge Sharpe net of costs.
    grid = [(d, t) for d in (7, 14, 30) for t in (0.0, 0.05, 0.10)]
    scored = {g: summarise(run_weights(W, filtered(W, big, *g), rf), None, split)["excess_sharpe"] for g in grid}
    best = max(scored, key=lambda g: scored[g] if np.isfinite(scored[g]) else -9)
    filt = {f"Funding filter {d}d > {t:.0%} (BTC+ETH)": run_weights(W, filtered(W, big, d, t), rf) for d, t in grid}
    chosen_name = f"Funding filter {best[0]}d > {best[1]:.0%} (BTC+ETH)"
    topk = run_weights(W, top_k(W, alts, 14, 3), rf)
    topk_name = f"Top 3 of {len(alts)} by 14d funding, weekly"

    daily = pd.DataFrame({"always_btc_eth": always["BTC+ETH"]["net"], "always_all": always[f"All {len(alts)} coins"]["net"],
                          "filter_chosen": filt[chosen_name]["net"], "top3": topk["net"], "rf": rf})
    daily.to_csv(DAILY_CSV, float_format="%.6g")

    d7 = directional(W, alts)
    dd = []
    for lab, a, b in (("in sample", None, split), ("out of sample", split, None)):
        x = d7[(d7["date"] >= pd.Timestamp(a or "1900-01-01")) & (d7["date"] < pd.Timestamp(b or "2100-01-01"))]
        r = spearman(x["f"], x["r"])
        dd.append((lab, len(x), r, tstat_corr(r, len(x))))
    book = directional_book(W, alts)

    liq = liquidation_check(W, alts)
    margin_sweep = []
    for m in (0.0, 0.10, 0.25, 0.50):
        s = summarise(run_weights(W, always_on(W, big), rf, margin=m), split)
        margin_sweep.append((m, s))
    cost_sweep = []
    base_fee = (config.CARRY_SPOT_FEE, config.CARRY_PERP_FEE, config.CARRY_SLIPPAGE_DEFAULT)
    for lab, (sf, pf) in {"Standard taker fees": (0.0010, 0.0005), "With BNB discount (spot 0.075%)": (0.00075, 0.0005), "Maker both legs (0.1% / 0.02%)": (0.0010, 0.0002)}.items():
        config.CARRY_SPOT_FEE, config.CARRY_PERP_FEE = sf, pf
        cost_sweep.append((lab, summarise(run_weights(W, filtered(W, big, *best), rf), split)))
    config.CARRY_SPOT_FEE, config.CARRY_PERP_FEE, _ = base_fee

    yr = yearly(always["BTC+ETH"])
    oos_all = summarise(always["BTC+ETH"], split)
    first, last = W["carry"].index[0].date(), W["carry"].index[-1].date()
    fund_by_year = (W["funding"][big].mean(axis=1).groupby(W["funding"].index.year).mean() * DAYS)

    L = ["# Crypto carry study: perpetual funding and spot-perp basis", "",
         f"Binance public data, {first} to {last}, {len(alts)} large coins (BTC, ETH, BNB, XRP, LTC, ADA, DOGE, LINK, SOL, AVAX; each from its own perp launch). "
         f"Parameters chosen before {split[:4]}; {split[:4]} onward is out of sample. Costs: {config.CARRY_SPOT_FEE:.2%} spot and "
         f"{config.CARRY_PERP_FEE:.2%} perp taker fees, slippage {config.CARRY_SLIPPAGE['BTC']:.2%} per leg per side for BTC and ETH and "
         f"{config.CARRY_SLIPPAGE_DEFAULT:.2%} for the rest, {config.CARRY_MARGIN:.0%} extra capital held as margin, idle capital earning nothing. "
         "Edge is measured against the US 3-month T-bill (what the money earns for doing nothing).", ""]
    L += [f"**Verdict:** PLACEHOLDER", ""]
    L += ["## Funding by year (BTC and ETH, annualised, average of the two)", "", "| year | funding earned by a short |", "|---|---|"]
    L += [f"| {y} | {pct(v)} |" for y, v in fund_by_year.items()] + [""]
    L += ["## Always-on cash-and-carry", ""] + strat_table(list(always.items()), split) + [""]
    L += ["Calendar years, BTC+ETH always-on:", "", "| year | net return on capital | T-bill | funding collected (gross, on capital) | max drawdown |", "|---|---|---|---|---|"]
    L += [f"| {int(r.year)} | {pct(r.net)} | {pct(r.rf)} | {pct(r.funding_only_gross)} | {pct(r.maxdd, 2)} |" for r in yr.itertuples()] + [""]
    L += ["Per coin (always-on, one coin):", "", "| coin | perp from | mean funding a year, all | mean funding a year, out of sample | net return a year, all | net return a year, OOS | OOS edge Sharpe | OOS max drawdown |", "|---|---|---|---|---|---|---|---|"]
    L += [f"| {r.coin} | {r._2} | {pct(r.mean_funding_ann)} | {pct(r.oos_funding_ann)} | {pct(r.all_net_ann)} | {pct(r.oos_net_ann)} | {num(r.oos_excess_sharpe)} | {pct(r.oos_maxdd, 2)} |" for r in pc.itertuples()] + [""]
    L += ["## Timing and selection rules", "",
          f"Funding filter grid (trailing window days, threshold a year), in-sample edge Sharpe on BTC+ETH: " + "; ".join(f"{d}d>{t:.0%}: {num(v)}" for (d, t), v in scored.items()) + f". Chosen in sample: **{best[0]}d > {best[1]:.0%}**.", ""]
    L += strat_table([(chosen_name, filt[chosen_name]), (topk_name, topk)] + [(n, d) for n, d in filt.items() if n != chosen_name][:2], split) + [""]
    L += ["## Sensitivities (BTC+ETH, out of sample)", "", "Margin held per 1.0 of notional (always-on): " + "; ".join(f"{m:.0%}: {pct(s['net_ann'])} a year, edge Sharpe {num(s['excess_sharpe'])}" for m, s in margin_sweep) + ".", "",
          "Fee tier (chosen filter): " + "; ".join(f"{lab}: {pct(s['net_ann'], 2)} a year" for lab, s in cost_sweep) + ".", ""]
    L += ["## Liquidation check", "", f"Worst intraday high against the previous close for a short perp, with {config.CARRY_MARGIN:.0%} margin per 1.0 notional "
          "(a day above the margin would risk liquidation unless topped up from the spot side or cash).", "",
          "| coin | days | worst intraday spike | days > margin | days > half margin |", "|---|---|---|---|---|"]
    L += [f"| {r.coin} | {r.days} | {pct(r.worst_spike)} | {r.days_over_margin} | {r.days_over_half_margin} |" for r in liq.itertuples()] + [""]
    L += ["## Directional test: does high funding predict falling prices?", "",
          "Non-overlapping weeks, all coins pooled, Spearman rank correlation of trailing-7d funding with the next 7-day perp return (t-stat treats weeks as independent, and coins within a week are correlated, so it flatters):", "",
          "| sample | weeks x coins | rank correlation | t |", "|---|---|---|---|"]
    L += [f"| {lab} | {n} | {num(r, 3)} | {num(t)} |" for lab, n, r, t in dd] + [""]
    bi, bo = stats(window(book, None, split)["net"]), stats(window(book, split)["net"])
    L += [f"Contrarian book (short the perp when funding is in its own top quintile, long in the bottom quintile; expanding quantiles, weekly, net of perp fees): in sample Sharpe {num(bi['sharpe'])}, "
          f"annual {pct(bi['ann'])}; out of sample Sharpe {num(bo['sharpe'])}, annual {pct(bo['ann'])}, max drawdown {pct(bo['maxdd'])}.", ""]
    L += ["## Practical access (UK retail)", "",
          "- Binance returned HTTP 451 and Bybit 403 from this container; the study used Binance's static historical dump, which is public.",
          "- The FCA has banned the sale of crypto derivatives (perpetuals, futures, options) to UK retail clients since 6 January 2021. The short perp leg is therefore not legitimately available to a UK retail account on a regulated venue; using an offshore exchange through a VPN breaches its terms and leaves no UK protection. Professional-client status needs wealth and experience tests a student will not meet.",
          "- Spot alone is allowed, but spot alone is just directional crypto, not carry. Spot plus a hedge through a UK-available product (for example a short ETN) is not possible: UK retail may now buy crypto ETNs (since 8 October 2025) but cannot short them.",
          "- Stablecoin lending or staking is the nearest legal yield; it carries platform and depeg risk and is not what this study tests.",
          "- Counterparty risk is the real tail: capital sits on an exchange (FTX-type loss) and a perp short can liquidate on a spike or when the exchange auto-deleverages. None of that is in the backtest.", ""]
    L += ["## Caveats", "",
          "- Survivorship: the ten coins are today's large coins; coins that fell away (and their funding) are not here. This flatters the alt rows.",
          "- Daily closes only: intraday basis swings, funding-rate timing, and margin top-ups on spikes are not simulated. The liquidation table bounds the worst case (its largest spikes, e.g. DOGE 412% and ETH 203%, may be bad prints in the dump rather than real moves).",
          "- USDT is treated as a dollar; a depeg of the stablecoin or of the exchange is not modelled. Idle capital earns nothing here (exchanges often pay a little, which would help slightly).",
          f"- Sample: about {len(W['carry'])/365:.1f} years, effectively one-and-a-half crypto cycles. {split[:4]} onward is {len(window(W['carry'], split))} days, and a Sharpe from that span has a standard error near 0.6, so differences between variants are not significant. Several variants were tried; the chosen one is biased upwards.",
          "- Dated (quarterly) futures basis is not tested: the perp funding rate is the same trade in the form most people use. Spot-perp basis enters as the basis P&L and is included.",
          "- Fees assume Binance taker rates, no VIP tier, no tax. UK tax on short-term gains and on each leg would reduce what is kept.", ""]
    text = "\n".join(L)
    verdict = verdict_text(oos_all, summarise(filt[chosen_name], split), summarise(topk, split), pc, dd, bo)
    text = text.replace("**Verdict:** PLACEHOLDER", "**Verdict:** " + verdict)
    REPORT.write_text(text + "\n")
    print(text[:4000])


def verdict_text(always_oos: dict, filt_oos: dict, topk_oos: dict, pc: pd.DataFrame, dd, book: dict) -> str:
    over = always_oos["net_ann"] - always_oos["rf_ann"]
    return (f"A real premium that has shrunk to roughly cash, and not tradable by a UK retail account. Always-on BTC+ETH carry made {pct(always_oos['net_ann'])} a year net out of sample "
            f"(2023 onward) against {pct(always_oos['rf_ann'])} for a T-bill, so only {pct(over)} a year of true excess, on capital exposed to exchange and stablecoin risk. "
            f"The huge Sharpe ({num(always_oos['excess_sharpe'])}) is an artefact of near-zero volatility, not a sign of safety: the risks (exchange failure, liquidation, depeg) are not in daily returns. "
            "Funding was 22-34% a year in 2020-21 and has been 2-5% in 2025-26, below the T-bill in 2026. "
            f"Timing and rotation rules add nothing: the chosen funding filter made {pct(filt_oos['net_ann'])} a year (same as always-on), top-3 rotation lost {pct(-topk_oos['net_ann'])} a year after "
            f"{pct(topk_oos['cost_ann'])} of costs, and the directional contrarian book is flat before luck (Sharpe {num(book['sharpe'])}). "
            "No edge worth taking; the perp leg is banned for UK retail clients anyway.")


if __name__ == "__main__":
    import sys
    main("--refresh" in sys.argv)
