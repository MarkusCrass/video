"""Password gate helpers (constant-time comparison, simple lockout)."""

from __future__ import annotations

import hmac
import time

from studio import config

MAX_ATTEMPTS = 5
LOCK_SECONDS = 30


def check_password(entered: str) -> bool:
    """Return True when `entered` matches APP_PASSWORD (constant-time)."""
    return hmac.compare_digest(
        entered.encode("utf-8"), config.APP_PASSWORD.encode("utf-8")
    )


def lock_remaining(state: dict) -> int:
    """Seconds left in the lockout window for this browser session (0 = none)."""
    until = float(state.get("lock_until", 0.0))
    return max(0, int(until - time.time()))


def register_failure(state: dict) -> None:
    """Count a failed attempt; lock the session after MAX_ATTEMPTS failures."""
    state["fails"] = int(state.get("fails", 0)) + 1
    if state["fails"] >= MAX_ATTEMPTS:
        state["fails"] = 0
        state["lock_until"] = time.time() + LOCK_SECONDS
