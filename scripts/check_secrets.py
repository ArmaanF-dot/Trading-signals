"""Fail (exit 1) if any tracked file looks like it contains a secret. Run in CI."""
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "ntfy topic URL": re.compile(r"ntfy\.sh/(?!\{)[A-Za-z0-9_-]{8,}"),
    "NTFY_TOPIC assignment": re.compile(r"NTFY_TOPIC\s*[:=]\s*['\"]?[A-Za-z0-9_-]{6,}"),
    "SEC_USER_AGENT with email": re.compile(r"SEC_USER_AGENT\s*[:=]\s*['\"]?[^'\"\n]*@[^'\"\n]+"),
    "email-bearing User-Agent": re.compile(r"User-Agent['\"]?\s*[:=]\s*['\"][^'\"]*[\w.+-]+@[\w-]+\.[\w.]+"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic api key": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9/+_-]{16,}['\"]"),
}
SKIP = {"scripts/check_secrets.py", "tests/test_check_secrets.py"}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f not in SKIP]


def scan_text(text: str) -> list[str]:
    return [name for name, pat in PATTERNS.items() if pat.search(text)]


def main() -> int:
    bad = []
    for f in tracked_files():
        p = Path(f)
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        bad += [f"{f}: {n}" for n in scan_text(text)]
        if p.name == ".env" or p.suffix == ".env":
            bad.append(f"{f}: env file is tracked")
    for b in bad:
        print("SECRET?", b)  # never prints the matched value
    print("check_secrets:", "FAILED" if bad else "ok")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
