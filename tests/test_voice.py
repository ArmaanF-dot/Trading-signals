import numpy as np
import pandas as pd

from edge.voice import collect, features

CATALOGUE = '''const L=[
 {n:"Deere & Co Earnings Call Podcast ($DE)",s:"deere-co-earnings-call",a:"x",c: 5 },
 {n:"Berkshire Hathaway Inc Earnings Call Podcast ($BRK.B)",s:"berkshire-earnings-call",a:"x",c: 4 },
 {n:"No ticker here",s:"nope",a:"x",c: 4 },
];'''

FEED = '''<rss><channel>
<item><title>Deere ($DE) Q4 2026 Earnings Call</title><pubDate>Tue, 25 Nov 2026 00:00:00 +0000</pubDate>
<guid>g1</guid><enclosure url="https://casti.fyi/audio/a/1.mp3" length="0" type="audio/mpeg"/></item>
<item><title>Deere ($DE) Q3 2026 Earnings Call</title><pubDate>Wed, 20 Aug 2026 00:00:00 +0000</pubDate>
<guid>g0</guid><enclosure url="https://casti.fyi/audio/a/0.mp3" length="0" type="audio/mpeg"/></item>
<item><title>no audio</title><pubDate>Wed, 20 Aug 2026 00:00:00 +0000</pubDate></item>
</channel></rss>'''

CAL = {"data": {"rows": [
    {"symbol": "DE", "time": "time-pre-market", "marketCap": "$172,835,275,000"},
    {"symbol": "X", "time": "time-not-supplied", "marketCap": ""}]}}


def test_parsers():
    cat = collect.parse_catalogue(CATALOGUE)
    assert [c["ticker"] for c in cat] == ["DE", "BRK.B"]
    assert collect.parse_rss_id('<a href="/rss/b36592e77a525c0f109d1bc9.xml">') == "b36592e77a525c0f109d1bc9"
    eps = collect.parse_feed(FEED)
    assert [e["date"] for e in eps] == ["2026-11-25", "2026-08-20"]
    assert collect.pick_episodes(eps, {"g1"})[0]["guid"] == "g0"
    c = collect.parse_calendar(CAL)
    assert c["DE"] == {"timing": "bmo", "mcap": 172835275000} and c["X"]["timing"] == "unknown"


def test_parse_bars_handles_junk():
    assert collect.parse_bars({}).empty
    p = {"chart": {"result": [{"timestamp": [1, 2], "indicators": {"quote": [
        {"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1.0, None], "volume": [5, 6]}]}}]}}
    assert len(collect.parse_bars(p)) == 1


def synth(seconds_pattern, sr=features.SR):
    """Voiced bursts (harmonic tone with vibrato) separated by silences: [(kind, seconds, f0)]."""
    out = []
    rng = np.random.default_rng(0)
    for kind, sec, f0 in seconds_pattern:
        n = int(sec * sr)
        if kind == "sil":
            out.append(rng.normal(0, 1e-4, n))
        else:
            t = np.arange(n) / sr
            f = f0 * (1 + 0.03 * np.sin(2 * np.pi * 4 * t))
            ph = 2 * np.pi * np.cumsum(f) / sr
            env = 0.5 + 0.5 * np.sin(2 * np.pi * 4 * t) ** 2  # ~8 syllables a second
            out.append(0.3 * env * (np.sin(ph) + 0.5 * np.sin(2 * ph) + 0.25 * np.sin(3 * ph)))
    return np.concatenate(out).astype(np.float32)


def test_pauses_pitch_and_rate():
    x = synth([("sil", 1, 0), ("v", 6, 120), ("sil", 1.5, 0), ("v", 6, 120), ("sil", 0.5, 0), ("v", 6, 120), ("sil", 1, 0)])
    e = features.energy_db(x)
    sp = features.voice_activity(e)
    segs = features.runs(sp)
    assert len(segs) == 3 and abs(sum(b - a for a, b in segs) / 100 - 18) < 1
    f0 = features.pitch_track(x, len(e))
    semis = np.nanmedian(f0[sp])
    assert abs(semis - 12 * np.log2(120 / 100)) < 0.7
    nuc = features.nuclei(e, f0, sp)
    assert 100 < nuc.sum() < 180  # about 8 per second over 18 s


def test_analyse_two_voices_and_summary():
    # a low "executive" voice with long prepared remarks, then short alternating higher analyst turns
    pat = [("v", 20, 110), ("sil", 2, 0)] * 6
    for _ in range(8):
        pat += [("v", 6, 220), ("sil", 1, 0), ("v", 14, 110), ("sil", 2, 0)]
    rows, summ = features.analyse(synth(pat))
    assert rows and summ["turns"] == len(rows)
    assert summ["speakers"] >= 1 and summ["exec_speakers"] >= 1  # synthetic voices share a timbre: clustering is tested on real calls
    assert {"duration_min", "turns", "exec_speakers"} <= set(summ)


def test_run_end_to_end_offline(tmp_path):
    pages = {"https://casti.fyi/listen/earnings": CATALOGUE,
             "https://casti.fyi/listen/deere-co-earnings-call": '<a href="/rss/aaaaaaaaaaaaaaaaaaaa.xml">',
             "https://casti.fyi/listen/berkshire-earnings-call": "",
             "https://casti.fyi/rss/aaaaaaaaaaaaaaaaaaaa.xml": FEED}

    class R:
        def __init__(self, text="", js=None):
            self.text, self._js = text, js

        def json(self):
            if self._js is None:
                raise ValueError
            return self._js

    def get(url, headers=None, min_interval=0.0):
        if "nasdaq" in url:
            return R(js=CAL if "2026-11-25" in url else {"data": {"rows": None}})
        if "yahoo" in url:
            return R(js={})
        return R(pages[url])

    fake_rows = [{"turn": 0, "start": 0.0, "dur": 5.0, "speaker": 0, "role": "exec", "section": "prepared", "speech_s": 4.0,
                  "pauses": 1, "pause_mean": 0.4, "long_pauses": 0, "pitch_med": 1.0, "pitch_sd": 1.0, "pitch_p10": 0.0,
                  "pitch_p90": 2.0, "int_sd": 5.0, "nuclei": 20, "artic_rate": 4.0, "flat_voiced": 0, "latency": None}]
    got = []

    def analyse(x):
        return fake_rows, {"duration_min": 12.0, "turns": 1}

    def dl(url, dest):
        got.append(url)
        dest.write_bytes(b"x")
        return True

    # decode is not exercised offline: stub it to ten-plus minutes of silence
    orig = features.decode
    features.decode = lambda p, sr=features.SR: np.zeros(features.SR * 700, dtype=np.float32)
    try:
        n = collect.run(budget_s=60, data_dir=tmp_path, get=get, analyse=analyse, dl=dl, today="2026-11-27")
        n2 = collect.run(budget_s=60, data_dir=tmp_path, get=get, analyse=analyse, dl=dl, today="2026-11-27")
    finally:
        features.decode = orig
    assert n == 2 and n2 == 0 and len(got) == 2  # recent call and the August backfill, never repeated
    calls = pd.read_csv(tmp_path / "calls.csv")
    assert set(calls["ticker"]) == {"DE"} and "bmo" in set(calls["timing"])
    assert (tmp_path / "turns" / "2026-11.csv.gz").exists() and (tmp_path / "turns" / "2026-08.csv.gz").exists()
