"""Run the day scanner over a date range (one GitHub Actions matrix shard).

python run.py jets-history START END [SHARD NSHARDS]
Days already saved in data/jets/history are skipped, so reruns resume.
"""
import os
import sys
import time
from datetime import date, timedelta

import requests

from edge.jets import day as D
from edge.jets import registry


def main(argv: list[str]) -> int:
    start, end = date.fromisoformat(argv[0]), date.fromisoformat(argv[1])
    shard, n = (int(argv[2]), int(argv[3])) if len(argv) > 3 else (0, 1)
    watch = {r["hex"] for r in registry.load()}
    airports = D.Airports.from_csv_text(requests.get(D.AIRPORTS_URL, timeout=120).text)
    token = os.environ.get("GITHUB_TOKEN")
    d, i = start, 0
    while d <= end:
        if i % n == shard and not (D.HISTORY_DIR / f"{d.isoformat()}.csv").exists():
            t = time.time()
            try:
                rows, stats = D.run_day(d, watch, airports, token)
                if "error" not in stats:
                    D.save(d, rows)
                print(f"{d} rows={len(rows)} {stats} {time.time() - t:.0f}s", flush=True)
            except Exception as exc:  # one bad day must not kill the shard
                print(f"{d} failed: {type(exc).__name__}: {exc}", flush=True)
        d += timedelta(days=1)
        i += 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
