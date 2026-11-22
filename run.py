"""Entry point: python run.py form4|fca|combo|all"""
import sys

USAGE = "usage: python run.py form4|fca|combo|feed|all | backtest START_YEAR END_YEAR | opportunistic FIRST_YEAR LAST_YEAR | fca-study | momentum | dashboard"


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else ""
    if what == "dashboard":
        from edge import dashboard
        dashboard.main()
        return 0
    if what == "momentum":
        from edge import momentum
        momentum.main()
        return 0
    if what == "fca-study":
        from edge.fca import backtest as fb
        fb.main()
        return 0
    if what == "opportunistic":
        from edge.form4 import opportunistic
        opportunistic.main(int(argv[2]), int(argv[3]))
        return 0
    if what == "backtest":
        from edge.form4 import backtest
        backtest.main(int(argv[2]), int(argv[3]))
        return 0
    if what not in ("form4", "fca", "combo", "feed", "all"):
        print(USAGE)
        return 2
    failed = False
    steps = ["form4", "fca", "combo", "feed"] if what == "all" else [what]
    for step in steps:
        try:
            if step == "form4":
                from edge.form4 import run as m
                m.run()
            elif step == "fca":
                from edge.fca import run as m
                m.run()
            elif step == "feed":
                from edge import feed, track
                f = feed.run()
                track.run()
                print(f"feed: {len(f['signals'])} active signals")
            else:
                from edge import combo as m
                m.run()
        except Exception as exc:
            print(f"{step} failed: {type(exc).__name__}: {exc}")
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
