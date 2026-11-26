"""Entry point: python run.py form4|fca|combo|all"""
import sys

USAGE = "usage: python run.py form4|fca|combo|feed|all | backtest START_YEAR END_YEAR | opportunistic FIRST_YEAR LAST_YEAR | fca-study | pead-study | momentum | frontier | reversal | ml-rank | quality-value | oil-tanks | risk | dashboard | ufc PATH | jobs | jobs-study | jobs-deep"


def study_runner(what: str, argv: list[str]):
    """The backtest studies; each writes to reports/, after which the risk summary is rebuilt."""
    if what == "oil-tanks":
        from edge import oil_tanks
        return oil_tanks.main
    if what == "jobs-deep":
        from edge.jobs import deep
        return deep.main
    if what == "jobs-study":
        from edge.jobs import study
        return study.main
    if what == "pead-study":
        from edge import pead
        return pead.main
    if what == "quality-value":
        from edge import quality_value
        return quality_value.main
    if what == "ml-rank":
        from edge import ml_rank
        return ml_rank.main
    if what == "reversal":
        from edge import reversal
        return reversal.main
    if what == "frontier":
        from edge import frontier
        return frontier.main
    if what == "momentum":
        from edge import momentum
        return momentum.main
    if what == "fca-study":
        from edge.fca import backtest as fb
        return fb.main
    if what == "opportunistic":
        from edge.form4 import opportunistic
        return lambda: opportunistic.main(int(argv[2]), int(argv[3]))
    if what == "backtest":
        from edge.form4 import backtest
        return lambda: backtest.main(int(argv[2]), int(argv[3]))
    return None


def refresh_risk() -> None:
    """Rebuild reports/risk_summary.md|json (Sharpe, drawdown, leverage line) from the study outputs."""
    try:
        from edge import risk
        risk.run()
    except Exception as exc:  # a failed summary must not fail the study that just finished
        print(f"risk summary failed: {type(exc).__name__}: {exc}")


def main(argv: list[str]) -> int:
    what = argv[1] if len(argv) > 1 else ""
    if what == "dashboard":
        from edge import dashboard
        dashboard.main()
        return 0
    if what == "jobs":
        from edge.jobs import collect
        collect.run()
        return 0
    if what == "ufc":
        from edge import ufc
        return ufc.main(argv)
    if what == "risk":
        from edge import risk
        print(risk.run())
        return 0
    study = study_runner(what, argv)
    if study:
        study()
        refresh_risk()
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
