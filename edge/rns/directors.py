"""Director dealings: manual CSV for now (data/rns_director_buys.csv).

Columns: date, company, isin, ticker, director, role, shares, price, value_gbp, source_url
Add rows by hand from RNS "Director/PDMR Shareholding" notices (open-market purchases only).
"""
import pandas as pd

import config
from edge import store

COLUMNS = ["date", "company", "isin", "ticker", "director", "role", "shares", "price", "value_gbp", "source_url"]


def load() -> pd.DataFrame:
    df = store.read_csv(config.RNS_CSV)
    if df.empty:
        return pd.DataFrame(columns=COLUMNS)
    missing = {"date", "isin"} - set(df.columns)
    if missing:
        raise ValueError(f"{config.RNS_CSV.name} missing columns: {sorted(missing)}")
    df["isin"] = df["isin"].str.strip().str.upper()
    return df
