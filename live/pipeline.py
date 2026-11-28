"""Ties it together: audio chunks -> phrases -> (transcript, audio features) -> analyser.

Capture never waits for the transcriber: closed phrases go on a queue and one worker thread transcribes
them, so a slow CPU shows up as "behind by N s" rather than lost audio.
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Callable, Iterable

import numpy as np

from live.engine import CallAnalyser, Flag, phrase_features
from live.segmenter import Phrase, Segmenter


class Pipeline:
    def __init__(self, analyser: CallAnalyser, transcriber: Callable[[np.ndarray, str], str],
                 on_flag: Callable[[Flag, "Pipeline"], None] | None = None, status: dict | None = None):
        self.analyser, self.transcriber, self.on_flag = analyser, transcriber, on_flag
        self.lock = threading.Lock()
        self.seg = Segmenter()
        self.q: queue.Queue = queue.Queue()
        self.status = {"state": "starting", "behind_s": 0.0, **(status or {})}
        self.audio_s = 0.0
        self.error: str | None = None
        self._worker = threading.Thread(target=self._work, daemon=True)
        self._worker.start()
        self._last_text = ""

    # -- producers ------------------------------------------------------------------------------
    def feed(self, chunk: np.ndarray) -> None:
        self.audio_s += len(chunk) / 16000
        for ph in self.seg.feed(chunk):
            self.q.put(ph)
        self._update_behind()

    def run(self, chunks: Iterable[np.ndarray], stop: Callable[[], bool] = lambda: False) -> None:
        self.status["state"] = "listening"
        for c in chunks:
            if stop():
                break
            self.feed(c)
        self.finish()

    def finish(self) -> None:
        for ph in self.seg.flush():
            self.q.put(ph)
        self.q.put(None)
        self._worker.join()
        with self.lock:
            for f in self.analyser.finish():
                self._notify(f)
        self.status["state"] = "finished"

    # -- consumer -------------------------------------------------------------------------------
    def _update_behind(self) -> None:
        pending = sum(1 for _ in list(self.q.queue)) if self.q.qsize() else 0
        newest = self.analyser.elapsed
        self.status["behind_s"] = round(max(0.0, self.audio_s - newest), 1) if pending else 0.0

    def _work(self) -> None:
        while True:
            ph: Phrase | None = self.q.get()
            if ph is None:
                return
            try:
                text = self.transcriber(ph.audio, self._last_text)
                feats = phrase_features(ph.audio)
                with self.lock:
                    flags = self.analyser.add_phrase(ph.start, ph.end, ph.gap_before, feats, text)
                    for f in flags:
                        self._notify(f)
                self._last_text = text
            except Exception as e:      # keep the call going; show the problem in the UI
                self.error = f"{type(e).__name__}: {e}"

    def _notify(self, f: Flag) -> None:
        if self.on_flag:
            self.on_flag(f, self)

    def snapshot(self) -> dict:
        with self.lock:
            s = self.analyser.snapshot()
        s["status"] = dict(self.status, audio_s=round(self.audio_s, 1), error=self.error)
        return s
