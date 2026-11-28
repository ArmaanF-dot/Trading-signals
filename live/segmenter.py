"""Cuts a stream of 16 kHz mono audio into phrases at pauses, as the audio arrives.

A phrase ends after PHRASE_GAP seconds of silence (or MAX_PHRASE seconds of speech). The gap between
one phrase and the next is kept, because pauses are one of the cues: the engine decides whether a gap
is a breath, a hesitation or a long pause.

Speech/silence uses frame energy against a noise floor and speech level learned from the last 30 s,
the same idea as edge.voice.features.voice_activity but incremental.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

SR = 16000
HOP = 160           # 10 ms
WIN = 400           # 25 ms
PHRASE_GAP = 0.60   # s of silence that closes a phrase
MIN_PHRASE = 0.80   # s of speech below which a burst is dropped (clicks, breaths, "mm")
MAX_PHRASE = 25.0   # s


@dataclass
class Phrase:
    start: float          # seconds from the start of capture
    end: float
    audio: np.ndarray     # float32, 16 kHz mono, includes ~0.1 s of margin before the speech
    gap_before: float     # silence between the previous phrase's end and this one's start (s)


class Segmenter:
    def __init__(self, phrase_gap: float = PHRASE_GAP, min_phrase: float = MIN_PHRASE, max_phrase: float = MAX_PHRASE):
        self.phrase_gap, self.min_phrase, self.max_phrase = phrase_gap, min_phrase, max_phrase
        self._tail = np.zeros(0, dtype=np.float32)      # samples not yet turned into frames
        self._buf: list[np.ndarray] = []                # audio of the open phrase (including lead-in)
        self._hist: deque[float] = deque(maxlen=3000)   # frame energies (dB), 30 s
        self._frames_seen = 0
        self._speech_run = 0
        self._sil_run = 0
        self._in_phrase = False
        self._start_frame = 0
        self._last_end_frame: int | None = None
        self._lead: deque[np.ndarray] = deque(maxlen=10)  # last 100 ms of audio before speech opens a phrase

    def feed(self, x: np.ndarray) -> list[Phrase]:
        """Add audio, return any phrases that have just closed."""
        out: list[Phrase] = []
        x = np.concatenate([self._tail, x.astype(np.float32)])
        n = (len(x) - WIN) // HOP + 1 if len(x) >= WIN else 0
        for i in range(n):
            seg = x[i * HOP:i * HOP + WIN]
            e = 10 * np.log10(float(np.mean(seg.astype(np.float64) ** 2)) + 1e-10)
            p = self._step(e, x[i * HOP:(i + 1) * HOP])
            if p is not None:
                out.append(p)
        self._tail = x[n * HOP:]
        return out

    def flush(self) -> list[Phrase]:
        """End of stream: close an open phrase."""
        if self._in_phrase:
            p = self._close(self._frames_seen - self._sil_run)
            return [p] if p is not None else []
        return []

    def _threshold(self) -> float:
        h = np.fromiter(self._hist, dtype=np.float64)
        floor, level = np.percentile(h, 10), np.percentile(h, 90)
        return floor + 0.35 * max(level - floor, 6.0)

    def _step(self, e: float, hop: np.ndarray) -> Phrase | None:
        self._hist.append(e)
        f = self._frames_seen
        self._frames_seen += 1
        speech = len(self._hist) >= 30 and e > self._threshold()
        if not self._in_phrase:
            self._lead.append(hop)
            if speech:
                self._speech_run += 1
                if self._speech_run >= 8:   # 80 ms of speech opens a phrase
                    self._in_phrase = True
                    self._start_frame = f - self._speech_run + 1
                    self._buf = list(self._lead)
                    self._sil_run = 0
            else:
                self._speech_run = 0
            return None
        self._buf.append(hop)
        self._sil_run = 0 if speech else self._sil_run + 1
        if self._sil_run >= self.phrase_gap * 100:
            return self._close(f - self._sil_run + 1)
        if (f - self._start_frame - self._sil_run) / 100.0 >= self.max_phrase:
            return self._close(f + 1)
        return None

    def _close(self, end_frame: int) -> Phrase | None:
        audio = np.concatenate(self._buf) if self._buf else np.zeros(0, dtype=np.float32)
        start = self._start_frame
        gap = (start - self._last_end_frame) / 100.0 if self._last_end_frame is not None else 0.0
        self._in_phrase = False
        self._speech_run = 0
        self._sil_run = 0
        self._buf = []
        self._lead.clear()
        if (end_frame - start) / 100.0 < self.min_phrase:
            return None
        self._last_end_frame = end_frame
        return Phrase(start / 100.0, end_frame / 100.0, audio, round(gap, 2))
