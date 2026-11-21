"""ntfy notifications. Without NTFY_TOPIC, prints to stdout (dry run)."""
import requests

import config


def _header_safe(text: str) -> str:
    # HTTP headers must be latin-1; drop anything else rather than crash.
    return text.encode("latin-1", "ignore").decode("latin-1")


def send(title: str, message: str, priority: str = "default", tags: list[str] | None = None) -> bool:
    """Send an alert. Returns True if sent (or dry-run printed)."""
    topic = config.ntfy_topic()
    if not topic:
        print(f"[DRY RUN - NTFY_TOPIC not set] {title}\n{message}\n")
        return True
    headers = {"Title": _header_safe(title), "Priority": priority}
    if tags:
        headers["Tags"] = ",".join(tags)
    try:
        # The topic is a secret: never log the URL or the topic itself.
        resp = requests.post(
            f"{config.NTFY_BASE_URL}/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=config.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"ntfy send failed: {type(exc).__name__}")
        return False
