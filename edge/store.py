"""CSV helpers shared by the signals."""
from pathlib import Path

import pandas as pd


def read_csv(path) -> pd.DataFrame:
    """Read a CSV with every column as str (keeps CIK leading zeros). Empty if missing."""
    path = Path(path)
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame()
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def append_dedupe(path, new: pd.DataFrame, key: list[str]) -> pd.DataFrame:
    """Append rows of `new` not already in the CSV (matched on `key`). Returns rows added."""
    path = Path(path)
    if new.empty:
        return new
    old = read_csv(path)
    seen = set(map(tuple, old[key].values)) if not old.empty else set()
    keep = []
    for k in map(tuple, new[key].astype(str).values):
        keep.append(k not in seen)
        seen.add(k)
    added = new[keep]
    if added.empty:
        return added
    combined = pd.concat([old, added.astype(str)], ignore_index=True) if not old.empty else added.astype(str)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return added
