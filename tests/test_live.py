import functools
import json
import urllib.request
import wave

import numpy as np

from edge import calls, textchg
from live import audio, demo, words
from live.engine import CallAnalyser, SpeakerTracker, phrase_features
from live.pipeline import Pipeline
from live.segmenter import Segmenter
from live.server import make_server
from live.transcribe import ScriptedTranscriber


@functools.lru_cache(maxsize=None)
def run_demo():
    x, lines = demo.build()
    an = CallAnalyser(qa_min_elapsed=60, min_role_talk=30)
    pl = Pipeline(an, ScriptedTranscriber(lines))
    pl.run(audio.file_chunks(x, speed=0))
    return an, pl, x, lines


def test_word_lists_match_the_study():
    assert words.NEG == textchg.NEG and words.POS == textchg.POS and words.UNC == textchg.UNC
    assert words.HEDGE == calls.HEDGE and words.CERTAIN == calls.CERTAIN
    assert words.HEDGE_PHRASES == calls.HEDGE_PHRASES and words.FILLER_WORDS == calls.FILLER_WORDS
    assert words.FILLER_PHRASES == calls.FILLER_PHRASES


def test_text_stats_and_deflection():
    s = words.text_stats("Perhaps, I think demand is somewhat weak and losses are a concern, um, you know.")
    assert s["hedge"] >= 3 and s["neg"] >= 2 and s["filler"] >= 2
    assert words.deflection("what is the margin outlook", "It is too early to say how things will go for the margin this year really") \
        == 'opens with "too early to say"'
    assert words.deflection("q", "short") is None


def test_segmenter_finds_phrases_and_gaps():
    rng = np.random.default_rng(0)
    quiet = lambda s: rng.normal(0, 4e-4, int(s * 16000)).astype(np.float32)
    x = np.concatenate([quiet(2), demo.synth("ceo", "one two three four five six", rng=rng), quiet(1.5),
                        demo.synth("ceo", "seven eight nine ten eleven twelve", rng=rng), quiet(1)])
    seg = Segmenter()
    out = []
    for i in range(0, len(x), 8000):           # fed in half-second pieces, as live
        out += seg.feed(x[i:i + 8000])
    out += seg.flush()
    assert len(out) == 2
    assert abs(out[0].start - 2.0) < 0.2 and abs(out[1].gap_before - 1.5) < 0.3


def test_phrase_features_pitch_and_rate():
    a = phrase_features(demo.synth("ceo", "one two three four five six seven eight", syl_hz=4.5))
    b = phrase_features(demo.synth("ceo", "one two three four five six seven eight", syl_hz=3.0))
    assert abs(a["pitch_med"] - 12 * np.log2(112 / 100)) < 0.8
    assert a["nuclei"] / a["speech_s"] > b["nuclei"] / b["speech_s"] * 1.2


def test_voices_are_separated_and_roles_found():
    an, pl, x, lines = run_demo()
    assert pl.error is None
    assert len(an.phrases) == len(lines)
    assert len({p.speaker for p in an.phrases}) == 5
    ceo = {p.speaker for p, (v, *_rest) in zip(an.phrases, demo.script()) if v == "ceo"}
    assert len(ceo) == 1 and next(iter(ceo)) in an.mgmt
    assert an.role(an.first_speaker) == "operator"
    assert an.qa_start is not None and 130 < an.qa_start < 150


def test_cues_fire_on_the_demo_call():
    an, *_ = run_demo()
    kinds = {f.kind for f in an.flags}
    assert {"hedging", "negative", "pause", "slow_answer", "sidestep", "rate", "pitch", "section"} <= kinds
    slow = [f for f in an.flags if f.kind == "slow_answer"]
    assert slow and slow[0].severity == "alert"
    # nothing fires in the calm scripted remarks before questions start
    assert not [f for f in an.flags if f.t < an.qa_start and f.kind != "section"]
    assert an.latencies() and max(an.latencies()) > 4


def test_prepared_vs_qa_shift_and_summary():
    an, *_ = run_demo()
    assert any("slower in Q&A" in x for x in an.shift_lines())
    assert any("Hedging is higher in Q&A" in x for x in an.shift_lines())
    s = an.final_summary()
    assert "colour, not a validated trade signal" in s and "## Flagged cues" in s and "Answer latency" in s
    snap = an.snapshot()
    assert snap["section"] == "qa" and snap["flags"] and json.dumps(snap)


def test_speaker_tracker_keeps_one_voice_together():
    rng = np.random.default_rng(0)
    base = rng.normal(0, 4, 13)
    tr = SpeakerTracker()
    ids = [tr.assign(base + rng.normal(0, 0.5, 13), None, 1.0) for _ in range(12)]
    assert len(set(ids)) == 1
    assert tr.assign(base + 12, None, 1.0) != ids[0]


def test_wav_loading_and_resampling(tmp_path):
    t = np.arange(44100 * 2) / 44100
    x = (0.3 * np.sin(2 * np.pi * 440 * t) * 32767).astype(np.int16)
    p = tmp_path / "t.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(44100), w.writeframes(x.tobytes())
    y = audio.load_file(str(p))
    assert abs(len(y) - 32000) < 5 and 0.2 < np.abs(y).max() < 0.35
    assert sum(len(c) for c in audio.file_chunks(y, 0.5, speed=0)) == len(y)


def test_server_serves_state_and_summary():
    an, pl, *_ = run_demo()
    srv = make_server(pl, port=0, demo=True)
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        state = json.loads(urllib.request.urlopen(base + "/api/state").read())
        assert state["status"]["demo"] is True and state["flags"] and "disclaimer" in state
        assert b"Live Call Analyser" in urllib.request.urlopen(base + "/").read()
        assert b"Call summary" in urllib.request.urlopen(base + "/api/summary").read()
    finally:
        srv.shutdown()
