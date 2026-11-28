"""Tiny local web server (standard library only) for the live view. Listens on 127.0.0.1 only."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).parent / "static"


def make_server(pipeline, port: int = 8765, demo: bool = False) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):  # keep the terminal quiet
            pass

        def _send(self, body: bytes, ctype: str, code: int = 200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                self._send((STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
            elif path == "/api/state":
                s = pipeline.snapshot()
                s["status"]["demo"] = demo
                self._send(json.dumps(s).encode(), "application/json")
            elif path == "/api/summary":
                with pipeline.lock:
                    text = pipeline.analyser.final_summary()
                self._send(text.encode(), "text/markdown; charset=utf-8")
            else:
                self._send(b"not found", "text/plain", 404)

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
