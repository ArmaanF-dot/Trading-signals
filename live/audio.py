"""Audio sources: Windows system-audio capture (WASAPI loopback) and audio files.

All sources yield float32 mono chunks at 16 kHz. Capture needs no access to the company or the webcast
player: it records what your PC is playing, the same as hearing it through the speakers.
"""
from __future__ import annotations

import queue
import time
import wave
from pathlib import Path
from typing import Iterator

import numpy as np

SR = 16000


def resample(x: np.ndarray, sr_in: int, sr_out: int = SR) -> np.ndarray:
    """Cheap resampler (box low-pass then linear interpolation). Good enough for speech features."""
    if sr_in == sr_out or len(x) == 0:
        return x.astype(np.float32)
    if sr_in > sr_out:
        k = max(1, int(round(sr_in / sr_out)))
        if k > 1:
            x = np.convolve(x, np.ones(k) / k, mode="same")
    n_out = int(len(x) * sr_out / sr_in)
    t = np.arange(n_out) * (sr_in / sr_out)
    return np.interp(t, np.arange(len(x)), x).astype(np.float32)


def load_file(path: str) -> np.ndarray:
    """Any audio file -> 16 kHz mono float32. WAV needs nothing extra; other formats need ffmpeg on PATH."""
    p = Path(path)
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as w:
                ch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
                raw = w.readframes(n)
            if sw == 2:
                x = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                if ch > 1:
                    x = x.reshape(-1, ch).mean(1)
                return resample(x, sr)
        except wave.Error:
            pass
    from edge.voice import features
    return features.decode(str(p), SR)


def file_chunks(x: np.ndarray, chunk_s: float = 0.5, speed: float = 1.0) -> Iterator[np.ndarray]:
    """Replay audio as if live. speed 1 = real time, 0 = as fast as possible."""
    n = int(chunk_s * SR)
    for i in range(0, len(x), n):
        t0 = time.time()
        yield x[i:i + n]
        if speed > 0:
            time.sleep(max(0.0, chunk_s / speed - (time.time() - t0)))


def list_devices() -> list[str]:
    """Names of WASAPI loopback devices (Windows)."""
    import pyaudiowpatch as pa
    p = pa.PyAudio()
    try:
        return [f"{d['index']}: {d['name']}" for d in p.get_loopback_device_info_generator()]
    finally:
        p.terminate()


class LoopbackCapture:
    """Records the default output device's audio (whatever the PC is playing) via WASAPI loopback."""

    def __init__(self, device: int | None = None):
        import pyaudiowpatch as pa
        self.pa = pa
        self.p = pa.PyAudio()
        self.q: queue.Queue = queue.Queue(maxsize=600)
        self.stream = None
        self.dev = self._pick(device)
        self.name = self.dev["name"]
        self.rate = int(self.dev["defaultSampleRate"])
        self.channels = int(self.dev["maxInputChannels"])
        self.dropped = 0

    def _pick(self, device: int | None) -> dict:
        pa, p = self.pa, self.p
        if device is not None:
            return p.get_device_info_by_index(device)
        wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
        out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if out.get("isLoopbackDevice"):
            return out
        for lb in p.get_loopback_device_info_generator():
            if out["name"] in lb["name"]:
                return lb
        raise RuntimeError("No loopback device found for the default speakers. Run: python -m live --list-devices")

    def _cb(self, data, frames, t, status):
        try:
            self.q.put_nowait(data)
        except queue.Full:
            self.dropped += 1
        return (None, self.pa.paContinue)

    def start(self) -> None:
        self.stream = self.p.open(format=self.pa.paInt16, channels=self.channels, rate=self.rate, input=True,
                                  frames_per_buffer=int(self.rate * 0.1), input_device_index=self.dev["index"],
                                  stream_callback=self._cb)

    def chunks(self, stop) -> Iterator[np.ndarray]:
        """Yield 16 kHz mono chunks until stop() is true."""
        while not stop():
            try:
                data = self.q.get(timeout=0.3)
            except queue.Empty:
                continue
            x = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            if self.channels > 1:
                x = x.reshape(-1, self.channels).mean(1)
            yield resample(x, self.rate)

    def close(self) -> None:
        try:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
        finally:
            self.p.terminate()
