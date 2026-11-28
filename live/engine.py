"""The analysis engine: one phrase of audio plus its transcript in, cues and summaries out.

Nothing in here touches a microphone, a model or the network, so it is fully testable offline.

Audio features come from edge.voice.features (the earnings-call audio collector, PR #49): energy based
voice activity, Praat pitch in semitones, syllable-nucleus speaking rate, pauses, flat voiced stretches.
Text cues use the word lists of the language study (live/words.py mirrors edge/textchg.py and
edge/calls.py).

Per phrase (a stretch of speech between pauses of 0.6 s or more) we get a voice print, the phrase is
assigned to a speaker by online clustering, and phrases from the same speaker close together join into
a turn. Cues fire when a phrase or turn looks unusual against the call so far, or against that speaker's
own running baseline.

IMPORTANT: cues are colour, not a validated trade signal. See DISCLAIMER.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

from edge.voice import features as F
from live import words

SR = F.SR
TURN_GAP = 2.0          # s: same-speaker phrases closer than this join into one turn
LONG_PAUSE = 1.0        # s: counted as a long pause (matches the audio collector)
FLAG_LONG_PAUSE = 1.5   # s: a mid-answer pause this long is flagged
SLOW_ANSWER = 2.5       # s between a question ending and the answer starting
VERY_SLOW_ANSWER = 4.0
MIN_BASELINE = 8        # phrases of a speaker's own before deviation cues are shown
COOLDOWN = 60.0         # s between repeats of the same voice cue for one speaker
MGMT_SHARE = 0.15       # share of talk time that makes a voice "management" before Q&A starts
MIN_ROLE_TALK = 60.0    # s of total speech before roles are assigned
MIN_QA_ELAPSED = 300.0  # s into the call before Q&A can be detected

DISCLAIMER = ("These cues are colour, not a validated trade signal. The repo's studies found no return edge "
              "from transcript wording (reports/calls_study.md) and the audio test is still collecting data "
              "(reports/voice_feasibility.md). Speaker separation is crude and the transcript can be wrong.")

QA_TRIGGER = re.compile(r"first question|next question|our next question|begin the question|open (up )?the (line|floor)|"
                        r"now (open|take)|take (your|our|the) questions|q&a", re.I)

SEVERITY_ORDER = {"alert": 2, "watch": 1, "info": 0}


@dataclass
class Flag:
    t: float
    kind: str
    severity: str     # info | watch | alert
    speaker: int
    text: str

    def as_dict(self, label) -> dict:
        return {"t": round(self.t, 1), "kind": self.kind, "severity": self.severity,
                "speaker": label(self.speaker), "text": self.text}


@dataclass
class PhraseRec:
    idx: int
    start: float
    end: float
    speaker: int
    section: str
    text: str
    gap_before: float
    speech_s: float
    voiced_s: float
    nuclei: int
    pitch_med: float | None
    pitch_sd: float | None
    pitch_p10: float | None
    pitch_p90: float | None
    int_sd: float | None
    pauses: list[float]
    flat: int
    ts: dict
    turn: int = 0


def phrase_features(audio: np.ndarray) -> dict:
    """Audio features of one phrase, plus the voice print used for speaker clustering."""
    e = F.energy_db(audio)
    n = len(e)
    if n < 10:
        return {"speech_s": 0.0, "voiced_s": 0.0, "nuclei": 0, "pitch_med": None, "pitch_sd": None, "pitch_p10": None,
                "pitch_p90": None, "int_sd": None, "pauses": [], "flat": 0, "print": None}
    sp = F.voice_activity(e)
    padded = audio if len(audio) >= SR else np.concatenate([audio, np.zeros(SR - len(audio), dtype=audio.dtype)])
    f0 = F.pitch_track(padded, n)
    nuc = F.nuclei(e, f0, sp)
    segs = F.runs(sp)
    pauses: list[float] = []
    if segs:
        s0, s1 = segs[0][0], segs[-1][1]          # trim the lead-in and tail: only pauses between speech count
        pauses = [(b - a) / 100.0 for a, b in F.runs(~sp[s0:s1]) if (b - a) >= F.MIN_PAUSE * 100]
    pv = f0[np.isfinite(f0)]
    mf = F.mfcc(audio)[:n]
    vp = None
    if sp.sum() >= 20:
        med = float(np.median(pv)) if len(pv) else 0.0
        vp = np.concatenate([mf[sp].mean(0)[1:13], [med * 0.5]])
    return {
        "speech_s": float(sp.sum() / 100.0), "voiced_s": float(len(pv) / 100.0), "nuclei": int(nuc.sum()),
        "pitch_med": float(np.median(pv)) if len(pv) >= 20 else None,
        "pitch_sd": float(np.std(pv)) if len(pv) >= 20 else None,
        "pitch_p10": float(np.percentile(pv, 10)) if len(pv) >= 20 else None,
        "pitch_p90": float(np.percentile(pv, 90)) if len(pv) >= 20 else None,
        "int_sd": float(np.std(e[sp])) if sp.any() else None,
        "pauses": pauses, "flat": F.flat_voiced(f0, 0, n), "print": vp,
    }


class SpeakerTracker:
    """Online speaker clustering on voice prints (crude, see README)."""

    def __init__(self, threshold: float = 1.0, max_speakers: int = 10, prior_sd: float = 3.0):
        self.threshold, self.max_speakers, self.prior_sd = threshold, max_speakers, prior_sd
        self.centroids: list[np.ndarray] = []
        self.counts: list[int] = []
        self._all: list[np.ndarray] = []

    def _scale(self) -> np.ndarray:
        d = len(self.centroids[0]) if self.centroids else 13
        n = len(self._all)
        var = np.var(np.array(self._all), axis=0) if n > 1 else np.zeros(d)
        return np.sqrt((n * var + 5 * self.prior_sd ** 2) / (n + 5))

    def distances(self, v: np.ndarray) -> list[float]:
        sc = self._scale()
        return [float(np.sqrt(np.mean(((v - c) / sc) ** 2))) for c in self.centroids]

    def assign(self, v: np.ndarray | None, prev: int | None, gap: float) -> int:
        if v is None:                                   # too little voiced speech to tell: keep the previous voice
            return prev if prev is not None else self._new(np.zeros(13))
        if not self.centroids:
            self._all.append(v)
            return self._new(v)
        d = self.distances(v)
        k = int(np.argmin(d))
        near = d[k]
        # continuous speech (short gap) rarely changes speaker: be more reluctant to open a new voice
        thr = self.threshold * (1.5 if gap < 0.8 and prev is not None and k == prev else 1.0)
        self._all.append(v)
        if near <= thr or len(self.centroids) >= self.max_speakers:
            c = min(self.counts[k], 30)
            self.centroids[k] = (self.centroids[k] * c + v) / (c + 1)
            self.counts[k] += 1
            return k
        return self._new(v)

    def _new(self, v: np.ndarray) -> int:
        self.centroids.append(np.array(v, dtype=float))
        self.counts.append(1)
        return len(self.centroids) - 1


class CallAnalyser:
    def __init__(self, speaker_threshold: float = 1.0, qa_min_elapsed: float = MIN_QA_ELAPSED,
                 min_role_talk: float = MIN_ROLE_TALK):
        self.qa_min_elapsed, self.min_role_talk = qa_min_elapsed, min_role_talk
        self.tracker = SpeakerTracker(speaker_threshold)
        self.phrases: list[PhraseRec] = []
        self.flags: list[Flag] = []
        self.section = "prepared"
        self.qa_start: float | None = None
        self.mgmt: set[int] = set()
        self.first_speaker: int | None = None
        self.elapsed = 0.0
        self._last_flag: dict[tuple[int, str], float] = {}
        self._turn_no = -1
        self._turn_end = 0.0
        self._turn_speaker: int | None = None
        self._finalised_turn = -1
        self._qa_hint_alt = 0

    # -- speakers and roles ------------------------------------------------------------------------
    def label(self, s: int) -> str:
        return "Voice " + (chr(ord("A") + s) if s < 26 else str(s))

    def talk(self) -> dict[int, float]:
        t: dict[int, float] = {}
        for p in self.phrases:
            t[p.speaker] = t.get(p.speaker, 0.0) + p.speech_s
        return t

    def _update_roles(self) -> None:
        talk = self.talk()
        tot = sum(talk.values())
        if tot < self.min_role_talk:
            return
        if self.qa_start is None:
            self.mgmt = {s for s, v in talk.items() if v / tot >= MGMT_SHARE and v >= 20}
        else:                                           # in Q&A: keep management, add anyone who clearly keeps talking
            self.mgmt |= {s for s, v in talk.items() if v >= 90 and v / tot >= 0.10 and s != self.first_speaker}

    def role(self, s: int) -> str:
        if s in self.mgmt:
            return "management"
        if sum(self.talk().values()) < self.min_role_talk:
            return "speaker"
        if s == self.first_speaker:
            return "operator"
        return "analyst" if self.qa_start is not None else "other"

    # -- main entry --------------------------------------------------------------------------------
    def add_phrase(self, start: float, end: float, gap_before: float, audio_feats: dict, text: str) -> list[Flag]:
        """Add one phrase. Returns the flags it raised."""
        prev = self.phrases[-1].speaker if self.phrases else None
        spk = self.tracker.assign(audio_feats.get("print"), prev, gap_before)
        if self.first_speaker is None:
            self.first_speaker = spk
        self.elapsed = max(self.elapsed, end)

        new_turn = not (prev == spk and gap_before < TURN_GAP and self._turn_speaker == spk)
        if new_turn:
            self._finalise_turn(self._turn_no)
            self._turn_no += 1
        within_gap = gap_before if not new_turn else None
        self._turn_speaker, self._turn_end = spk, end

        pauses = list(audio_feats["pauses"])
        if within_gap is not None and within_gap >= F.MIN_PAUSE:
            pauses.append(within_gap)
        rec = PhraseRec(len(self.phrases), start, end, spk, self.section, text.strip(), gap_before,
                        audio_feats["speech_s"], audio_feats["voiced_s"], audio_feats["nuclei"], audio_feats["pitch_med"],
                        audio_feats["pitch_sd"], audio_feats["pitch_p10"], audio_feats["pitch_p90"], audio_feats["int_sd"],
                        pauses, audio_feats["flat"], words.text_stats(text), self._turn_no)
        self.phrases.append(rec)
        self._update_roles()
        raised: list[Flag] = []

        self._detect_qa(rec, raised)
        rec.section = self.section
        self._pause_cues(rec, within_gap, new_turn, raised)
        self._latency_cue(rec, new_turn, raised)
        self._text_cues(rec, raised)
        self._voice_cues(rec, raised)
        self.flags.extend(raised)
        return raised

    def finish(self) -> list[Flag]:
        """End of call: close the last turn (answer-level cues need the whole answer)."""
        before = len(self.flags)
        self._finalise_turn(self._turn_no)
        return self.flags[before:]

    # -- cue detectors -----------------------------------------------------------------------------
    def _emit(self, out: list[Flag], t: float, kind: str, sev: str, spk: int, text: str, cooldown: float = 0.0) -> None:
        key = (spk, kind)
        if cooldown and t - self._last_flag.get(key, -1e9) < cooldown:
            return
        self._last_flag[key] = t
        out.append(Flag(t, kind, sev, spk, text))

    def _who(self, spk: int) -> str:
        r = self.role(spk)
        return f"{self.label(spk)} ({r})" if r not in ("speaker", "other") else self.label(spk)

    def _detect_qa(self, rec: PhraseRec, out: list[Flag]) -> None:
        if self.qa_start is not None or rec.end < self.qa_min_elapsed:
            return
        hit = bool(QA_TRIGGER.search(rec.text))
        others = {p.turn for p in self.phrases if p.speaker not in self.mgmt and p.start >= rec.end - 600
                  and p.speaker != self.first_speaker}
        if (hit and self.mgmt) or (self.mgmt and len(others) >= 3):
            self.section = "qa"
            self.qa_start = rec.start
            self._emit(out, rec.start, "section", "info", rec.speaker, "Question-and-answer session appears to have started "
                       "(prepared-remarks versus Q&A comparisons now begin).")

    def _pause_cues(self, rec: PhraseRec, within_gap: float | None, new_turn: bool, out: list[Flag]) -> None:
        if rec.speaker not in self.mgmt and self.role(rec.speaker) != "speaker":
            return
        if within_gap is not None and within_gap >= FLAG_LONG_PAUSE:
            self._emit(out, rec.start, "pause", "watch", rec.speaker,
                       f"{self._who(rec.speaker)} paused for {within_gap:.1f} s mid-answer.")
        internal = max([p for p in rec.pauses if p is not within_gap] or [0.0])
        if internal >= FLAG_LONG_PAUSE:
            self._emit(out, rec.start, "pause", "watch", rec.speaker,
                       f"{self._who(rec.speaker)} paused for {internal:.1f} s mid-sentence.")

    def _latency_cue(self, rec: PhraseRec, new_turn: bool, out: list[Flag]) -> None:
        if not new_turn or self.section != "qa" or rec.speaker not in self.mgmt or rec.idx == 0:
            return
        prev = self.phrases[rec.idx - 1]
        if prev.speaker in self.mgmt:
            return
        lat = rec.start - prev.end
        rec.ts["latency"] = lat
        if lat >= VERY_SLOW_ANSWER:
            self._emit(out, rec.start, "slow_answer", "alert", rec.speaker,
                       f"Slow to answer: {lat:.1f} s between the question ending and {self._who(rec.speaker)} starting.")
        elif lat >= SLOW_ANSWER:
            self._emit(out, rec.start, "slow_answer", "watch", rec.speaker,
                       f"Slowish to answer: {lat:.1f} s before {self._who(rec.speaker)} replied.")

    def _text_cues(self, rec: PhraseRec, out: list[Flag]) -> None:
        ts = rec.ts
        if ts["words"] < 6:
            return
        who = self._who(rec.speaker)
        if ts["hedge"] >= 2:
            self._emit(out, rec.start, "hedging", "watch", rec.speaker,
                       f"Hedging from {who}: {', '.join(repr(w) for w in ts['hedge_words'][:4])}.", cooldown=15)
        if ts["neg"] >= 2 or (ts["neg"] >= 1 and ts["neg"] > ts["pos"] and ts["words"] <= 14):
            self._emit(out, rec.start, "negative", "watch", rec.speaker,
                       f"Negative language from {who}: {', '.join(repr(w) for w in ts['neg_words'][:5])}.", cooldown=15)
        if ts["unc"] >= 2:
            self._emit(out, rec.start, "uncertainty", "info", rec.speaker, f"Uncertainty wording from {who}.", cooldown=30)
        if ts["filler"] >= 2:
            self._emit(out, rec.start, "filler", "info", rec.speaker,
                       f"Several filler words from {who} (transcribers often drop these, so this is a minimum).", cooldown=30)

    def _finalise_turn(self, turn: int) -> None:
        """Answer-level cues once a turn is complete."""
        if turn < 0 or turn <= self._finalised_turn:
            return
        self._finalised_turn = turn
        ph = [p for p in self.phrases if p.turn == turn]
        if not ph or ph[0].section != "qa" or ph[0].speaker not in self.mgmt:
            return
        prior = [p for p in self.phrases if p.turn == turn - 1]
        if not prior or prior[0].speaker in self.mgmt:
            return
        q = " ".join(p.text for p in prior)
        a = " ".join(p.text for p in ph)
        why = words.deflection(q, a)
        if why:
            f = Flag(ph[-1].end, "sidestep", "watch", ph[0].speaker,
                     f"Possible sidestep by {self._who(ph[0].speaker)}: the answer {why}.")
            self.flags.append(f)

    def _voice_cues(self, rec: PhraseRec, out: list[Flag]) -> None:
        spk = rec.speaker
        if self.role(spk) == "operator" or rec.speech_s < 2.0:
            return
        mine = [p for p in self.phrases if p.speaker == spk and p.speech_s >= 2.0]
        if len(mine) < MIN_BASELINE + 3:
            return
        recent, base = mine[-3:], mine[:-3]

        def z(vals_base, vals_recent, floor):
            vb = np.array([v for v in vals_base if v is not None], dtype=float)
            vr = np.array([v for v in vals_recent if v is not None], dtype=float)
            if len(vb) < MIN_BASELINE or len(vr) < 2 or vb.std() < 1e-6:
                return None
            diff = vr.mean() - vb.mean()
            return diff, diff / (max(vb.std(), floor) / np.sqrt(len(vr)))

        rate = lambda p: p.nuclei / p.speech_s if p.speech_s else None
        who = self._who(spk)
        r = z([rate(p) for p in base], [rate(p) for p in recent], 0.4)
        if r and abs(r[1]) >= 2.5:
            mu = np.mean([rate(p) for p in base])
            pct = r[0] / mu * 100 if mu else 0
            if abs(pct) >= 12:
                self._emit(out, rec.end, "rate", "watch", spk,
                           f"{who} is speaking {abs(pct):.0f}% {'faster' if pct > 0 else 'slower'} than their own norm.", COOLDOWN)
        r = z([p.pitch_med for p in base], [p.pitch_med for p in recent], 0.8)
        if r and abs(r[1]) >= 2.5 and abs(r[0]) >= 1.0:
            self._emit(out, rec.end, "pitch", "watch", spk,
                       f"{who}'s pitch is {abs(r[0]):.1f} semitones {'higher' if r[0] > 0 else 'lower'} than their own norm.", COOLDOWN)
        r = z([p.pitch_sd for p in base], [p.pitch_sd for p in recent], 0.4)
        if r and abs(r[1]) >= 2.5 and abs(r[0]) >= 0.7:
            self._emit(out, rec.end, "pitch_var", "info", spk,
                       f"{who}'s pitch is {'more animated' if r[0] > 0 else 'flatter'} than their own norm.", COOLDOWN)

    # -- summaries ---------------------------------------------------------------------------------
    def _agg(self, ph: list[PhraseRec]) -> dict | None:
        sp = sum(p.speech_s for p in ph)
        w = sum(p.ts["words"] for p in ph)
        if sp < 20 or w < 40:
            return None

        def wavg(attr):
            xs = [(getattr(p, attr), p.speech_s) for p in ph if getattr(p, attr) is not None]
            return sum(a * b for a, b in xs) / sum(b for _, b in xs) if xs else None

        c = lambda k: sum(p.ts[k] for p in ph)
        return {"speech_s": sp, "words": w,
                "pitch_med": wavg("pitch_med"), "pitch_sd": wavg("pitch_sd"),
                "rate": sum(p.nuclei for p in ph) / sp,
                "wpm": w / sp * 60,
                "pauses_pm": sum(len(p.pauses) for p in ph) / sp * 60,
                "long_pauses_pm": sum(1 for p in ph for d in p.pauses if d >= LONG_PAUSE) / sp * 60,
                "hedge_100": c("hedge") / w * 100, "neg_100": c("neg") / w * 100, "pos_100": c("pos") / w * 100,
                "unc_100": c("unc") / w * 100, "filler_100": c("filler") / w * 100,
                "tone_100": (c("pos") - c("neg")) / w * 100}

    def _mgmt_phrases(self, section: str | None = None, since: float | None = None) -> list[PhraseRec]:
        return [p for p in self.phrases if p.speaker in self.mgmt and (section is None or p.section == section)
                and (since is None or p.start >= since)]

    def latencies(self) -> list[float]:
        return [p.ts["latency"] for p in self.phrases if "latency" in p.ts]

    def shift_lines(self) -> list[str]:
        """Plain-English prepared-remarks versus Q&A differences for management voices."""
        a, b = self._agg(self._mgmt_phrases("prepared")), self._agg(self._mgmt_phrases("qa"))
        if not a or not b:
            return []
        lines = []
        pct = lambda x, y: (x - y) / y * 100 if y else 0.0
        d = pct(b["rate"], a["rate"])
        if abs(d) >= 8:
            lines.append(f"Management speaks {abs(d):.0f}% {'faster' if d > 0 else 'slower'} in Q&A than in prepared remarks.")
        if a["pitch_med"] is not None and b["pitch_med"] is not None and abs(b["pitch_med"] - a["pitch_med"]) >= 0.5:
            dp = b["pitch_med"] - a["pitch_med"]
            lines.append(f"Average pitch is {abs(dp):.1f} semitones {'higher' if dp > 0 else 'lower'} in Q&A.")
        if a["pitch_sd"] and b["pitch_sd"] and abs(pct(b["pitch_sd"], a["pitch_sd"])) >= 15:
            d = pct(b["pitch_sd"], a["pitch_sd"])
            lines.append(f"Pitch variation is {abs(d):.0f}% {'wider' if d > 0 else 'flatter'} in Q&A.")
        if abs(b["pauses_pm"] - a["pauses_pm"]) >= 2 and abs(pct(b["pauses_pm"], a["pauses_pm"])) >= 25:
            lines.append(f"Pauses are {'more' if b['pauses_pm'] > a['pauses_pm'] else 'less'} frequent in Q&A "
                         f"({b['pauses_pm']:.0f} against {a['pauses_pm']:.0f} a minute).")
        if abs(b["hedge_100"] - a["hedge_100"]) >= 0.5:
            lines.append(f"Hedging is {'higher' if b['hedge_100'] > a['hedge_100'] else 'lower'} in Q&A "
                         f"({b['hedge_100']:.1f} against {a['hedge_100']:.1f} per 100 words).")
        if abs(b["tone_100"] - a["tone_100"]) >= 0.6:
            lines.append(f"Word tone is {'more positive' if b['tone_100'] > a['tone_100'] else 'more negative'} in Q&A "
                         f"(net {b['tone_100']:+.1f} against {a['tone_100']:+.1f} per 100 words).")
        return lines

    def rolling_lines(self, window: float = 180.0) -> list[str]:
        """Last `window` seconds of management against management's call so far."""
        now = self.elapsed
        recent = self._agg(self._mgmt_phrases(since=now - window))
        whole = self._agg(self._mgmt_phrases())
        if not recent or not whole:
            return []
        lines = []
        pct = lambda x, y: (x - y) / y * 100 if y else 0.0
        d = pct(recent["rate"], whole["rate"])
        if abs(d) >= 8:
            lines.append(f"Management is speaking {abs(d):.0f}% {'faster' if d > 0 else 'slower'} than their call average.")
        if abs(recent["hedge_100"] - whole["hedge_100"]) >= 0.7:
            lines.append(f"Hedging is {'up' if recent['hedge_100'] > whole['hedge_100'] else 'down'}: "
                         f"{recent['hedge_100']:.1f} per 100 words against {whole['hedge_100']:.1f} on average.")
        if abs(recent["tone_100"] - whole["tone_100"]) >= 0.8:
            lines.append(f"Word tone has turned {'more positive' if recent['tone_100'] > whole['tone_100'] else 'more negative'} "
                         f"(net {recent['tone_100']:+.1f} per 100 words, call average {whole['tone_100']:+.1f}).")
        if recent["long_pauses_pm"] > whole["long_pauses_pm"] + 1.0:
            lines.append("Long pauses are more frequent than earlier in the call.")
        if not lines:
            lines.append("Nothing unusual in the last few minutes against management's own call so far.")
        return lines

    def counts(self) -> dict:
        c: dict[str, int] = {}
        for f in self.flags:
            c[f.kind] = c.get(f.kind, 0) + 1
        return c

    def snapshot(self, turns: int = 30, flags: int = 60) -> dict:
        talk = self.talk()
        speakers = [{"id": s, "label": self.label(s), "role": self.role(s), "talk_s": round(v, 1)}
                    for s, v in sorted(talk.items())]
        # newest turn last: merge phrases of a turn
        by_turn: dict[int, dict] = {}
        for p in self.phrases:
            t = by_turn.setdefault(p.turn, {"turn": p.turn, "t": round(p.start, 1), "speaker": self.label(p.speaker),
                                            "role": self.role(p.speaker), "section": p.section, "text": ""})
            t["text"] = (t["text"] + " " + p.text).strip()
            t["role"] = self.role(p.speaker)
        a, b = self._agg(self._mgmt_phrases("prepared")), self._agg(self._mgmt_phrases("qa"))
        lat = self.latencies()
        return {
            "elapsed": round(self.elapsed, 1), "section": self.section, "qa_start": self.qa_start,
            "speakers": speakers, "turns": list(by_turn.values())[-turns:],
            "flags": [f.as_dict(self.label) for f in self.flags[-flags:]][::-1], "counts": self.counts(),
            "rolling": self.rolling_lines(), "shift": self.shift_lines(),
            "metrics": {"prepared": a, "qa": b, "latency_mean": float(np.mean(lat)) if lat else None},
            "series": [{"t": round(p.start, 1), "rate": round(p.nuclei / p.speech_s, 2), "pitch_sd": p.pitch_sd,
                        "pitch": p.pitch_med} for p in self.phrases[-120:]
                       if p.speaker in self.mgmt and p.speech_s >= 2.0],
            "disclaimer": DISCLAIMER,
        }

    def final_summary(self) -> str:
        """Plain-text/Markdown summary of the whole call."""
        s = self.snapshot(turns=10_000, flags=10_000)
        m = lambda x: f"{x:.1f}"
        out = [f"# Call summary", "", f"_{DISCLAIMER}_", ""]
        mins = self.elapsed / 60
        out.append(f"Captured {mins:.1f} minutes, {len(self.phrases)} phrases, {len(s['speakers'])} distinct voices. "
                   + (f"Q&A seems to start at {self.qa_start / 60:.1f} min." if self.qa_start is not None
                      else "No Q&A section was detected (the call may have been cut short or the detector may have missed it)."))
        out += ["", "## Voices", ""]
        for sp in s["speakers"]:
            out.append(f"- {sp['label']}: {sp['role']}, {sp['talk_s'] / 60:.1f} min of speech")
        for name, key in (("Management, prepared remarks", "prepared"), ("Management, Q&A", "qa")):
            g = s["metrics"][key]
            if g:
                out += ["", f"## {name}", "",
                        f"- Speaking rate {g['rate']:.2f} syllables a second ({g['wpm']:.0f} words a minute)",
                        f"- Pitch {m(g['pitch_med']) if g['pitch_med'] is not None else 'n/a'} semitones re 100 Hz, spread "
                        f"{m(g['pitch_sd']) if g['pitch_sd'] is not None else 'n/a'}",
                        f"- Pauses {g['pauses_pm']:.0f} a minute, long pauses (1 s+) {g['long_pauses_pm']:.1f} a minute",
                        f"- Per 100 words: hedging {g['hedge_100']:.1f}, negative {g['neg_100']:.1f}, positive {g['pos_100']:.1f}, "
                        f"uncertainty {g['unc_100']:.1f}, filler {g['filler_100']:.1f}"]
        if s["shift"]:
            out += ["", "## Prepared remarks versus Q&A", ""] + [f"- {x}" for x in s["shift"]]
        lat = self.latencies()
        if lat:
            out += ["", "## Answer latency", "",
                    f"- {len(lat)} answers, mean {np.mean(lat):.1f} s, slowest {max(lat):.1f} s, "
                    f"{sum(1 for x in lat if x >= SLOW_ANSWER)} of them {SLOW_ANSWER:.1f} s or longer"]
        if self.flags:
            out += ["", "## Flagged cues", "", "Counts: " + ", ".join(f"{k} {v}" for k, v in sorted(s["counts"].items())), ""]
            top = sorted(self.flags, key=lambda f: (-SEVERITY_ORDER[f.severity], f.t))
            shown = [f for f in top if f.kind != "section"][:25]
            for f in sorted(shown, key=lambda f: f.t):
                out.append(f"- [{int(f.t // 60):02d}:{int(f.t % 60):02d}] {f.text}")
        else:
            out += ["", "## Flagged cues", "", "None raised."]
        out += ["", "## Reading this", "",
                "Compare against the same company's earlier calls before drawing anything from it: a speaker's own baseline "
                "matters more than any absolute number, and a single call is one observation."]
        return "\n".join(out) + "\n"
