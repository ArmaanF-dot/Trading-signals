import subprocess
import sys

from conftest import FIX
sys.path.insert(0, "scripts")
import check_secrets as cs  # noqa: E402


def test_flags_secret_looking_text():
    assert cs.scan_text("NTFY_TOPIC=my-long-random-topic-123")
    assert cs.scan_text("curl https://ntfy.sh/abcdefghij12345")
    assert cs.scan_text('SEC_USER_AGENT = "Jane Doe jane@example.com"')
    assert cs.scan_text("ghp_" + "a" * 36)
    assert cs.scan_text('api_key = "' + "A" * 24 + '"')


def test_allows_normal_code():
    assert not cs.scan_text('f"{config.NTFY_BASE_URL}/{topic}"')
    assert not cs.scan_text("NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}")
    assert not cs.scan_text("SEC_USER_AGENT: ${{ secrets.SEC_USER_AGENT }}")


def test_repo_is_clean():
    r = subprocess.run([sys.executable, "scripts/check_secrets.py"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
