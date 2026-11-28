"""Local speech-to-text with faster-whisper (CPU, int8). Nothing leaves the PC."""
from __future__ import annotations

import numpy as np


class WhisperTranscriber:
    def __init__(self, model: str = "small.en", language: str = "en", threads: int = 0):
        from faster_whisper import WhisperModel   # imported late: the engine and tests do not need it
        self.model_name = model
        self.language = language
        self.model = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=threads)

    def __call__(self, audio: np.ndarray, prompt: str = "") -> str:
        segs, _ = self.model.transcribe(audio.astype(np.float32), language=self.language, beam_size=1,
                                        condition_on_previous_text=False, vad_filter=False,
                                        initial_prompt=prompt[-200:] or None, temperature=0.0,
                                        no_speech_threshold=0.6)
        return " ".join(s.text.strip() for s in segs).strip()


class ScriptedTranscriber:
    """Hands back prepared text in order. Used by the demo and the tests, where there is no real speech."""

    def __init__(self, lines: list[str]):
        self.lines = list(lines)
        self.i = 0
        self.model_name = "scripted"

    def __call__(self, audio: np.ndarray, prompt: str = "") -> str:
        if self.i >= len(self.lines):
            return ""
        t = self.lines[self.i]
        self.i += 1
        return t
