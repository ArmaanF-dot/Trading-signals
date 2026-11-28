"""Vocal features from an earnings-call recording, without keeping the audio.

Pipeline (all CPU, numpy plus Praat via parselmouth, about a minute per hour of audio):

1. Decode to 16 kHz mono (ffmpeg).
2. Voice activity from frame energy (25 ms frames, 10 ms hop): speech, and pauses of 0.25 s or more.
3. Pitch track (Praat autocorrelation, 75-500 Hz), in semitones relative to 100 Hz so that
   male and female voices are comparable as changes.
4. Rough diarisation: speech is cut into chunks at pauses, each chunk gets a voice print (mean and
   spread of 13 MFCCs plus median pitch), chunks are clustered (agglomerative, number of speakers
   picked by silhouette), and runs of the same cluster become speaker turns. It is crude next to a
   neural diariser, but it separates the studio-quality executive voices from operator and
   telephone-quality analyst voices well, which is what the test needs.
5. Roles and sections: executive clusters are the ones that do most of the talking in the 10-40%
   stretch of the call (prepared remarks). Q&A starts at the first point after 15% of the call
   where non-executive voices take three or more turns of 3 s+ within ten minutes.
6. Per turn: pitch level/spread/range, intensity spread, syllable-nucleus rate (de Jong and Wempe
   style intensity peaks in voiced frames), pauses, long pauses (1 s+), flat voiced stretches (a
   proxy for filled pauses such as "uh" / "um"), and for executive turns in Q&A the latency
   between the end of the analyst's turn and the start of the answer.

Output: one row per turn and one summary row per call. Nothing here is a transcript and the audio
itself is discarded.
"""
from __future__ import annotations

import subprocess

import numpy as np

SR = 16000
HOP = 160          # 10 ms
WIN = 400          # 25 ms
MIN_PAUSE = 0.25   # s
LONG_PAUSE = 1.0   # s
CHUNK_PAUSE = 0.30  # s: speech is cut into chunks for diarisation at pauses this long
MIN_CHUNK = 1.0    # s: shorter chunks are merged into a neighbour before clustering
TURN_GAP = 2.0     # s: same-speaker chunks closer than this join into one turn

TURN_COLS = ["turn", "start", "dur", "speaker", "role", "section", "speech_s", "pauses", "pause_mean",
             "long_pauses", "pitch_med", "pitch_sd", "pitch_p10", "pitch_p90", "int_sd", "nuclei",
             "artic_rate", "flat_voiced", "latency"]


def decode(path: str, sr: int = SR) -> np.ndarray:
    """Any audio file -> float32 mono at `sr` Hz, via ffmpeg."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-i", str(path), "-ac", "1", "-ar", str(sr),
                          "-f", "s16le", "-"], check=True, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.int16).astype(np.float32) / 32768.0


def frames(x: np.ndarray, win: int = WIN, hop: int = HOP) -> np.ndarray:
    n = max(0, 1 + (len(x) - win) // hop)
    if n == 0:
        return np.zeros((0, win), dtype=np.float32)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    return x[idx]


def energy_db(x: np.ndarray) -> np.ndarray:
    out = []
    for start in range(0, len(x), HOP * 100_000):  # chunked to bound memory
        f = frames(x[start:start + HOP * 100_000 + WIN])
        out.append(10 * np.log10(np.mean(f.astype(np.float64) ** 2, axis=1) + 1e-10))
    e = np.concatenate(out) if out else np.zeros(0)
    return e[: max(0, 1 + (len(x) - WIN) // HOP)]


def runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """[start, end) index pairs of the True runs in a boolean array."""
    if len(mask) == 0:
        return []
    m = np.concatenate([[False], mask.astype(bool), [False]])
    d = np.diff(m.astype(np.int8))
    return list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def voice_activity(e: np.ndarray) -> np.ndarray:
    """Speech mask per frame: energy above a threshold between the noise floor and speech level,
    with gaps under 150 ms filled and bursts under 100 ms dropped."""
    if len(e) == 0:
        return np.zeros(0, dtype=bool)
    floor, level = np.percentile(e, 10), np.percentile(e, 90)
    speech = e > floor + 0.35 * (level - floor)
    for s, t in runs(~speech):
        if 0 < s and t < len(speech) and (t - s) < 15:
            speech[s:t] = True
    for s, t in runs(speech):
        if t - s < 10:
            speech[s:t] = False
    return speech


def pitch_track(x: np.ndarray, n_frames: int) -> np.ndarray:
    """F0 in semitones re 100 Hz per 10 ms frame (NaN when unvoiced), via Praat."""
    import parselmouth
    out = np.full(n_frames, np.nan)
    step = SR * 600  # ten-minute blocks keep Praat's memory use small
    for start in range(0, len(x), step):
        block = x[start:start + step]
        if len(block) < SR:
            continue
        p = parselmouth.Sound(block.astype(np.float64), SR).to_pitch_ac(time_step=0.01, pitch_floor=75, pitch_ceiling=500)
        f0 = p.selected_array["frequency"]
        t = p.xs() + start / SR
        idx = np.round((t - WIN / 2 / SR) / 0.01).astype(int)
        ok = (idx >= 0) & (idx < n_frames) & (f0 > 0)
        out[idx[ok]] = 12 * np.log2(f0[ok] / 100.0)
    return out


def mel_filterbank(n_mels: int = 26, n_fft: int = 512, sr: int = SR) -> np.ndarray:
    hz = lambda m: 700 * (10 ** (m / 2595) - 1)
    mel = lambda f: 2595 * np.log10(1 + f / 700)
    pts = hz(np.linspace(mel(60), mel(sr / 2 - 200), n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1))
    for i in range(1, n_mels + 1):
        a, b, c = bins[i - 1], bins[i], bins[i + 1]
        fb[i - 1, a:b] = (np.arange(a, b) - a) / max(b - a, 1)
        fb[i - 1, b:c] = (c - np.arange(b, c)) / max(c - b, 1)
    return fb


def mfcc(x: np.ndarray, n: int = 13) -> np.ndarray:
    """13 MFCCs per 10 ms frame."""
    fb = mel_filterbank()
    k = np.arange(26)
    dct = np.cos(np.pi / 26 * (k[None, :] + 0.5) * np.arange(n)[:, None])
    window = np.hamming(WIN)
    out = []
    for start in range(0, len(x), HOP * 50_000):
        f = frames(x[start:start + HOP * 50_000 + WIN]) * window
        spec = np.abs(np.fft.rfft(f, 512)) ** 2
        out.append(np.log(spec @ fb.T + 1e-10) @ dct.T)
    m = np.concatenate(out) if out else np.zeros((0, n))
    return m[: max(0, 1 + (len(x) - WIN) // HOP)]


def nuclei(e: np.ndarray, f0: np.ndarray, speech: np.ndarray) -> np.ndarray:
    """Boolean per frame: syllable nucleus (smoothed-intensity peak, at least 2 dB above the dips
    either side, voiced, inside speech)."""
    k = np.ones(5) / 5
    s = np.convolve(e, k, mode="same")
    peak = np.zeros(len(s), dtype=bool)
    if len(s) < 3:
        return peak
    cand = np.flatnonzero((s[1:-1] > s[:-2]) & (s[1:-1] >= s[2:])) + 1
    thr = np.median(s[speech]) - 2 if speech.any() else np.inf
    last = -10
    for i in cand:
        lo = s[max(0, i - 8):i].min() if i > 0 else s[i]
        hi = s[i + 1:i + 9].min() if i + 1 < len(s) else s[i]
        if s[i] >= thr and s[i] - lo >= 2 and s[i] - hi >= 2 and speech[i] and not np.isnan(f0[i]) and i - last >= 5:
            peak[i] = True
            last = i
    return peak


def flat_voiced(f0: np.ndarray, start: int, end: int) -> int:
    """Voiced stretches of 300 ms+ with almost no pitch movement (sd < 0.5 semitone): a proxy for
    filled pauses."""
    n = 0
    v = ~np.isnan(f0[start:end])
    for s, t in runs(v):
        if t - s >= 30 and np.nanstd(f0[start + s:start + t]) < 0.5:
            n += 1
    return n


def chunks(speech: np.ndarray) -> list[list[int]]:
    """Speech cut at pauses of CHUNK_PAUSE+, short chunks merged into the previous one."""
    gap = int(CHUNK_PAUSE * 100)
    segs = runs(speech)
    out: list[list[int]] = []
    for s, t in segs:
        if out and s - out[-1][1] < gap:
            out[-1][1] = t
        else:
            out.append([int(s), int(t)])
    merged: list[list[int]] = []
    for c in out:
        if merged and (c[1] - c[0] < MIN_CHUNK * 100 or merged[-1][1] - merged[-1][0] < MIN_CHUNK * 100) and c[0] - merged[-1][1] < 100:
            merged[-1][1] = c[1]
        else:
            merged.append(c)
    return merged


def cluster(prints: np.ndarray, max_k: int = 12) -> np.ndarray:
    """Speaker label per chunk: agglomerative (Ward) on standardised voice prints, k by silhouette."""
    from sklearn.cluster import AgglomerativeClustering
    from sklearn.metrics import silhouette_score
    n = len(prints)
    if n < 4:
        return np.zeros(n, dtype=int)
    z = (prints - prints.mean(0)) / (prints.std(0) + 1e-9)
    best, best_s = np.zeros(n, dtype=int), -1.0
    sample = np.random.default_rng(0).choice(n, size=min(n, 1500), replace=False)
    for k in range(2, min(max_k, n - 1) + 1):
        lab = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(z)
        s = silhouette_score(z[sample], lab[sample]) if len(set(lab[sample])) > 1 else -1
        if s > best_s + 0.005:
            best, best_s = lab, s
    # smooth one-chunk flickers: a chunk whose neighbours agree with each other takes their label
    lab = best.copy()
    for i in range(1, n - 1):
        if lab[i - 1] == lab[i + 1] != lab[i]:
            lab[i] = lab[i - 1]
    return lab


def roles(turns: list[dict], total_s: float) -> tuple[set[int], float | None]:
    """Executive speaker ids and the Q&A start time (s), see module docstring."""
    lo, hi = 0.10 * total_s, 0.40 * total_s
    talk: dict[int, float] = {}
    for t in turns:
        ov = max(0.0, min(t["start"] + t["dur"], hi) - max(t["start"], lo))
        talk[t["speaker"]] = talk.get(t["speaker"], 0.0) + ov
    tot = sum(talk.values()) or 1.0
    execs = {k for k, v in talk.items() if v / tot >= 0.08}
    qa = None
    others = [t for t in turns if t["speaker"] not in execs and t["dur"] >= 3 and t["start"] >= 0.15 * total_s]
    for i, t in enumerate(others):
        if sum(1 for u in others[i:] if u["start"] <= t["start"] + 600) >= 3:
            qa = t["start"]
            break
    return execs, qa


def analyse(x: np.ndarray) -> tuple[list[dict], dict]:
    """Audio (16 kHz mono float) -> (turn rows, call summary)."""
    e = energy_db(x)
    n = len(e)
    speech = voice_activity(e)
    f0 = pitch_track(x, n)
    m = mfcc(x)[:n]
    nuc = nuclei(e, f0, speech)
    total_s = n / 100.0

    ch = chunks(speech)
    prints = []
    for s, t in ch:
        p = f0[s:t]
        med = np.nanmedian(p) if np.isfinite(p).any() else 0.0
        prints.append(np.concatenate([m[s:t].mean(0), m[s:t].std(0), [med]]))
    labels = cluster(np.array(prints)) if prints else np.zeros(0, dtype=int)

    turns: list[dict] = []
    for (s, t), lab in zip(ch, labels):
        if turns and turns[-1]["speaker"] == lab and s - turns[-1]["_e"] < TURN_GAP * 100:
            turns[-1]["_e"] = t
        else:
            turns.append({"speaker": int(lab), "_s": s, "_e": t})
    for t in turns:
        t["start"], t["dur"] = t["_s"] / 100.0, (t["_e"] - t["_s"]) / 100.0
    execs, qa = roles(turns, total_s)

    rows = []
    prev_other_end = None
    for i, t in enumerate(turns):
        s, en = t["_s"], t["_e"]
        sp = speech[s:en]
        p = f0[s:en]
        pv = p[np.isfinite(p)]
        pauses = [(b - a) / 100 for a, b in runs(~sp) if (b - a) >= MIN_PAUSE * 100]
        speech_s = sp.sum() / 100
        voiced_s = np.isfinite(p).sum() / 100
        role = "exec" if t["speaker"] in execs else "other"
        section = "qa" if qa is not None and t["start"] >= qa else "prepared"
        latency = None
        if role == "exec" and section == "qa" and prev_other_end is not None:
            latency = round(max(0.0, (s - prev_other_end) / 100), 2)
        if role == "other":
            prev_other_end = en
        elif role == "exec":
            prev_other_end = None
        rows.append({
            "turn": i, "start": round(t["start"], 2), "dur": round(t["dur"], 2), "speaker": t["speaker"],
            "role": role, "section": section, "speech_s": round(speech_s, 2), "pauses": len(pauses),
            "pause_mean": round(float(np.mean(pauses)), 3) if pauses else 0.0,
            "long_pauses": sum(1 for d in pauses if d >= LONG_PAUSE),
            "pitch_med": round(float(np.median(pv)), 3) if len(pv) else None,
            "pitch_sd": round(float(np.std(pv)), 3) if len(pv) > 1 else None,
            "pitch_p10": round(float(np.percentile(pv, 10)), 3) if len(pv) else None,
            "pitch_p90": round(float(np.percentile(pv, 90)), 3) if len(pv) else None,
            "int_sd": round(float(np.std(e[s:en][sp])), 3) if sp.any() else None,
            "nuclei": int(nuc[s:en].sum()),
            "artic_rate": round(nuc[s:en].sum() / voiced_s, 3) if voiced_s > 0 else None,
            "flat_voiced": flat_voiced(f0, s, en), "latency": latency,
        })
    return rows, summarise(rows, total_s, qa)


def _agg(rows: list[dict]) -> dict:
    """Speech-time-weighted pitch/rate and per-minute pause counts over a set of turns."""
    sp = sum(r["speech_s"] for r in rows)
    if sp < 30:
        return {}
    w = lambda k: (sum(r[k] * r["speech_s"] for r in rows if r[k] is not None)
                   / (sum(r["speech_s"] for r in rows if r[k] is not None) or np.nan))
    lat = [r["latency"] for r in rows if r["latency"] is not None]
    return {"speech_min": round(sp / 60, 2), "pitch_med": round(w("pitch_med"), 3), "pitch_sd": round(w("pitch_sd"), 3),
            "pitch_range": round(w("pitch_p90") - w("pitch_p10"), 3), "int_sd": round(w("int_sd"), 3),
            "artic_rate": round(sum(r["nuclei"] for r in rows) / sp, 3),
            "pauses_pm": round(sum(r["pauses"] for r in rows) / sp * 60, 3),
            "long_pauses_pm": round(sum(r["long_pauses"] for r in rows) / sp * 60, 3),
            "flat_pm": round(sum(r["flat_voiced"] for r in rows) / sp * 60, 3),
            "pause_mean": round(np.mean([r["pause_mean"] for r in rows if r["pauses"]]) if any(r["pauses"] for r in rows) else 0.0, 3),
            "latency_mean": round(float(np.mean(lat)), 3) if lat else None}


def summarise(rows: list[dict], total_s: float, qa: float | None) -> dict:
    out = {"duration_min": round(total_s / 60, 2), "speakers": len({r["speaker"] for r in rows}),
           "exec_speakers": len({r["speaker"] for r in rows if r["role"] == "exec"}),
           "qa_start_min": round(qa / 60, 2) if qa is not None else None, "turns": len(rows)}
    for name, sel in [("prep", lambda r: r["role"] == "exec" and r["section"] == "prepared"),
                      ("qa", lambda r: r["role"] == "exec" and r["section"] == "qa"),
                      ("analyst", lambda r: r["role"] == "other" and r["section"] == "qa")]:
        for k, v in _agg([r for r in rows if sel(r)]).items():
            out[f"{name}_{k}"] = v
    # within-call shifts: executives under questioning versus their scripted remarks
    for k in ["pitch_med", "pitch_sd", "artic_rate", "pauses_pm", "long_pauses_pm", "flat_pm"]:
        a, b = out.get(f"qa_{k}"), out.get(f"prep_{k}")
        out[f"shift_{k}"] = round(a - b, 3) if a is not None and b is not None and np.isfinite(a) and np.isfinite(b) else None
    return out
