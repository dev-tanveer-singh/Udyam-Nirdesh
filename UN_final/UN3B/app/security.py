import threading
import time
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from .config import get_settings

ALGORITHM = "HS256"


# --------------------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:  # e.g. password longer than bcrypt's 72-byte limit
        return False


# Used to burn the same CPU time when an e-mail is unknown, so response timing does not
# reveal which addresses are registered.
_DUMMY_HASH = hash_password("not-a-real-password")


def burn_password_check(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


# --------------------------------------------------------------------------- tokens
def create_access_token(user_id: str, role: str) -> tuple[str, int]:
    s = get_settings()
    expires_in = s.access_token_expire_minutes * 60
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "role": role, "iat": now, "exp": now + timedelta(seconds=expires_in)}
    return jwt.encode(payload, s.secret_key, algorithm=ALGORITHM), expires_in


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None


# --------------------------------------------------------------------------- login throttling
class LoginThrottle:
    """Tiny in-memory limiter: N failed logins per (ip, email) inside a window.

    Per-process only -- behind several workers use Redis (or your API gateway) instead.
    """

    def __init__(self) -> None:
        self._failures: dict[tuple[str, str], list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key, now, window):
        hits = [t for t in self._failures.get(key, []) if now - t < window]
        if hits:
            self._failures[key] = hits
        else:
            self._failures.pop(key, None)
        return hits

    def is_blocked(self, ip: str, email: str) -> bool:
        s = get_settings()
        with self._lock:
            return len(self._recent((ip, email), time.monotonic(), s.login_lockout_seconds)) >= s.login_max_failed_attempts

    def record_failure(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.setdefault((ip, email), []).append(time.monotonic())

    def clear(self, ip: str, email: str) -> None:
        with self._lock:
            self._failures.pop((ip, email), None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_throttle = LoginThrottle()
