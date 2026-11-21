import pandas as pd

import config
from conftest import FIX
from edge import combo, notify
from edge.form4 import run as f4


def test_form4_end_to_end_offline(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for name, p in {"FORM4_BUYS_CSV": "b.csv", "FORM4_SEEN_TXT": "s.txt", "FORM4_CLUSTERS_CSV": "c.csv"}.items():
        monkeypatch.setattr(config, name, tmp_path / p)
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    xml = (FIX / "form4_buy.xml").read_text()
    second = xml.replace("0000222222", "0000333333").replace("Doe Jane", "Roe Rick").replace("2026-11-10", "2026-11-12")
    docs = {"i1": xml, "i2": second}
    monkeypatch.setattr(f4.fetch, "list_recent_filings",
                        lambda: [{"accession": "a1", "form_type": "4", "index_url": "i1"},
                                 {"accession": "a2", "form_type": "4", "index_url": "i2"}])
    monkeypatch.setattr(f4.fetch, "fetch_filing_xml", lambda u: docs[u])
    monkeypatch.setattr(f4.prices, "fetch_closes", lambda s: pd.Series(dtype=float))
    f4.run()
    assert "Insider cluster: ACME" in capsys.readouterr().out
    assert len(pd.read_csv(config.FORM4_CLUSTERS_CSV)) == 1
    f4.run()  # second run: nothing new, no duplicate alert
    assert "Insider cluster" not in capsys.readouterr().out
    assert len(pd.read_csv(config.FORM4_CLUSTERS_CSV)) == 1


def test_notify_dry_run_and_no_topic_leak(monkeypatch, capsys):
    monkeypatch.delenv("NTFY_TOPIC", raising=False)
    assert notify.send("t", "m")
    assert "DRY RUN" in capsys.readouterr().out
    monkeypatch.setenv("NTFY_TOPIC", "supersecrettopic")

    def boom(*a, **k):
        import requests
        raise requests.ConnectionError("https://ntfy.sh/supersecrettopic")
    monkeypatch.setattr(notify.requests, "post", boom)
    assert notify.send("t", "m") is False
    assert "supersecrettopic" not in capsys.readouterr().out


def test_run_py_usage(capsys):
    import run
    assert run.main(["run.py"]) == 2
