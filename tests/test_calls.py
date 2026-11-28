import numpy as np
import pandas as pd

from edge import calls


def turn(role, section, text):
    return {"role": role, "section": section, "text": text}


def test_part_features_counts_classes_and_skips_short_text():
    assert np.isnan(calls.part_features("good growth")["tone"])
    text = " ".join(["strong growth we believe maybe um you know risk decline --"] + ["filler"] * 300)
    f = calls.part_features(text)
    n = f["words"]
    assert f["tone"] == (2 - 1) / n  # strong, growth positive; decline negative
    assert f["unc"] == 2 / n  # believe, risk
    assert f["hedge"] >= 2 / n  # maybe, "we believe"
    assert f["disfl"] >= 3 / n  # um, you know, --


def test_call_features_split_by_role_and_section():
    pad = " ".join(["word"] * 400)
    turns = [turn("operator", "prepared", "welcome " + pad), turn("management", "prepared", "strong " + pad),
             turn("analyst", "qa", "weak " + pad), turn("management", "qa", "decline " + pad)]
    f = calls.call_features(turns)
    assert f["prep_tone"] > 0 and f["ans_tone"] < 0 and f["q_tone"] < 0
    assert f["prep_words"] == 401 and f["ans_words"] == 401


def test_add_changes_uses_only_previous_calls():
    d = pd.date_range("2020-01-01", periods=6, freq="90D")
    f = pd.DataFrame({"cik": "1", "date": d})
    for c in calls.LEVELS:
        f[c] = [1.0, 1.0, 1.0, 1.0, 1.0, 9.0]
    out = calls.add_changes(f)
    assert np.isnan(out["d_ans_tone"].iloc[0]) and np.isnan(out["d_ans_tone"].iloc[1])  # fewer than 2 prior calls
    assert out["d_ans_tone"].iloc[2] == 0.0
    assert out["d_ans_tone"].iloc[5] == 8.0  # the spike is not in its own baseline


def test_add_score_orients_signs_and_needs_all_parts():
    ev = pd.DataFrame({"filed": pd.to_datetime(["2023-01-10"] * 3)})
    for c in calls.SCORE_PARTS:
        ev[c] = [0.0, 1.0, 2.0]
    for c, s in calls.SCORE_PARTS.items():
        if s < 0:
            ev[c] = -ev[c]  # a bigger rise in a bad feature should score lower; negating flips it back
    ev.loc[0, "d_q_tone"] = np.nan
    out = calls.add_score(ev)
    assert np.isnan(out["call_score"].iloc[0])
    assert out["call_score"].iloc[2] > out["call_score"].iloc[1]
