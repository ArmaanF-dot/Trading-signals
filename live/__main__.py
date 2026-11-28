"""Command line: python -m live"""
from __future__ import annotations

import argparse
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m live", description="Live earnings-call analyser (local, free).")
    ap.add_argument("--file", help="analyse an audio file instead of live capture (wav needs nothing extra, others need ffmpeg)")
    ap.add_argument("--demo", action="store_true", help="run a synthetic call, no audio or model needed")
    ap.add_argument("--speed", type=float, default=None, help="file/demo replay speed: 1 = real time, 0 = as fast as possible "
                                                                "(default 1 for files, 30 for the demo)")
    ap.add_argument("--model", default="small.en", help="faster-whisper model: tiny.en, base.en, small.en (default), medium.en")
    ap.add_argument("--device", type=int, default=None, help="loopback device index (see --list-devices)")
    ap.add_argument("--list-devices", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--out-dir", default="live_runs", help="where the summary and transcript are saved (kept local, git-ignored)")
    ap.add_argument("--speaker-threshold", type=float, default=1.0, help="higher = fewer distinct voices (default 1.0)")
    a = ap.parse_args(argv)

    if a.list_devices:
        from live.audio import list_devices
        for d in list_devices():
            print(d)
        return 0

    from live import audio
    from live.engine import CallAnalyser
    from live.pipeline import Pipeline
    from live.server import make_server

    stop = threading.Event()
    status: dict = {}
    if a.demo:
        from live import demo
        from live.transcribe import ScriptedTranscriber
        x, lines = demo.build()
        analyser = CallAnalyser(a.speaker_threshold, qa_min_elapsed=60, min_role_talk=30)
        transcriber = ScriptedTranscriber(lines)
        speed = 30.0 if a.speed is None else a.speed
        chunks = audio.file_chunks(x, speed=speed)
        status["source"] = "demo"
        cap = None
    else:
        from live.transcribe import WhisperTranscriber
        print(f"Loading the {a.model} speech model (first run downloads it, about 0.5 GB for small.en)...", flush=True)
        transcriber = WhisperTranscriber(a.model)
        analyser = CallAnalyser(a.speaker_threshold)
        if a.file:
            x = audio.load_file(a.file)
            speed = 1.0 if a.speed is None else a.speed
            chunks = audio.file_chunks(x, speed=speed)
            status["source"] = Path(a.file).name
            cap = None
        else:
            try:
                cap = audio.LoopbackCapture(a.device)
            except ImportError:
                print("Live capture needs PyAudioWPatch (Windows only): pip install -r live/requirements.txt\n"
                      "To try the tool without it: python -m live --demo   or   python -m live --file some_call.wav")
                return 2
            cap.start()
            chunks = cap.chunks(stop.is_set)
            status["source"] = f"system audio: {cap.name}"
            print(f"Capturing: {cap.name}. Play the call in your browser; the view updates as it speaks.", flush=True)

    def on_flag(f, pl):
        mark = {"alert": "!!", "watch": " !", "info": "  "}[f.severity]
        print(f"[{int(f.t // 60):02d}:{int(f.t % 60):02d}] {mark} {f.text}", flush=True)

    pl = Pipeline(analyser, transcriber, on_flag, status)
    srv = make_server(pl, a.port, demo=a.demo)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Live view: {url}   (Ctrl+C to stop and print the call summary)", flush=True)
    if not a.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    t = threading.Thread(target=pl.run, args=(chunks, stop.is_set), daemon=True)
    t.start()
    try:
        while t.is_alive():
            time.sleep(0.3)
        if a.file or a.demo:
            print("\nFinished. The view stays up; press Ctrl+C to quit.", flush=True)
            summary_out(pl, a.out_dir)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    stop.set()
    print("\nStopping...", flush=True)
    if t.is_alive():
        t.join(timeout=120)
    if cap:
        cap.close()
    summary_out(pl, a.out_dir, show=True)
    srv.shutdown()
    return 0


_saved = False


def summary_out(pl, out_dir: str, show: bool = False) -> None:
    global _saved
    with pl.lock:
        text = pl.analyser.final_summary()
        transcript = "\n".join(f"[{int(p.start // 60):02d}:{int(p.start % 60):02d}] {pl.analyser.label(p.speaker)} "
                               f"({pl.analyser.role(p.speaker)}): {p.text}" for p in pl.analyser.phrases)
    if show or not _saved:
        print("\n" + text)
    if not _saved and pl.analyser.phrases:
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        (d / f"{stamp}_summary.md").write_text(text, encoding="utf-8")
        (d / f"{stamp}_transcript.txt").write_text(transcript + "\n", encoding="utf-8")
        print(f"Saved to {d / (stamp + '_summary.md')} and {d / (stamp + '_transcript.txt')} (local only, not committed).")
        _saved = True


if __name__ == "__main__":
    sys.exit(main())
