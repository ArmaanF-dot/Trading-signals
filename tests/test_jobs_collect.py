import json

import pandas as pd

from edge.jobs import collect


GH = {"jobs": [{"id": 1, "title": "Engineer"}, {"id": 2, "title": "Analyst"}], "meta": {"total": 2}}
LEVER = [{"id": "a-1", "text": "Engineer"}, {"id": "a-2", "text": "Sales"}, {"id": "a-3", "text": "Ops"}]
ASHBY = {"jobs": [{"id": "x", "isListed": True}, {"id": "y", "isListed": False}, {"id": "z"}]}


def test_posting_ids_per_ats():
    assert collect.posting_ids("greenhouse", GH) == {"1", "2"}
    assert collect.posting_ids("lever", LEVER) == {"a-1", "a-2", "a-3"}
    assert collect.posting_ids("ashby", ASHBY) == {"x", "z"}  # unlisted roles are not public openings


def test_diff_counts_added_and_removed_and_blank_on_first_day():
    assert collect.diff(None, {"1", "2"}) == (2, "", "")
    assert collect.diff({"1", "2", "3"}, {"2", "3", "4", "5"}) == (4, 2, 1)


def test_boards_file_is_well_formed():
    boards = collect.load_boards()
    assert len(boards) >= 50
    assert len({b["ticker"] for b in boards}) == len(boards)
    assert {b["ats"] for b in boards} <= set(collect.URLS)


def test_run_appends_daily_rows_keeps_state_on_error_and_skips_repeat_day(tmp_path, monkeypatch):
    boards = [{"ticker": "AAA", "ats": "greenhouse", "token": "aaa"}, {"ticker": "BBB", "ats": "lever", "token": "bbb"}]
    monkeypatch.setattr(collect, "load_boards", lambda: boards)
    day1 = {"https://boards-api.greenhouse.io/v1/boards/aaa/jobs": GH, "https://api.lever.co/v0/postings/bbb?mode=json": LEVER}
    collect.run("2026-11-26", get=day1.__getitem__, data_dir=tmp_path)

    def day2(url):
        if "lever" in url:
            raise ConnectionError("down")
        return {"jobs": [{"id": 2}, {"id": 3}, {"id": 4}]}

    collect.run("2026-11-27", get=day2, data_dir=tmp_path)
    collect.run("2026-11-27", get=day2, data_dir=tmp_path)  # second run the same day does nothing
    d = pd.read_csv(tmp_path / "daily.csv", dtype=str, keep_default_na=False)
    assert len(d) == 4
    a = d[(d["ticker"] == "AAA") & (d["date"] == "2026-11-27")].iloc[0]
    assert (a["open"], a["added"], a["removed"]) == ("3", "2", "1")
    b = d[(d["ticker"] == "BBB") & (d["date"] == "2026-11-27")].iloc[0]
    assert b["status"] == "error" and b["open"] == ""
    state = json.loads((tmp_path / "state.json").read_text())
    assert state["BBB"] == ["a-1", "a-2", "a-3"]  # failed fetch leaves yesterday's ids
