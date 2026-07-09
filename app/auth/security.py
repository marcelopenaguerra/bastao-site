import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

SESSION_DURATION = timedelta(hours=8)
SESSION_RENEW_THRESHOLD = timedelta(hours=1)
SESSION_COOKIE_NAME = "session_token"

_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, senha_hash: str) -> bool:
    try:
        return _hasher.verify(senha_hash, password)
    except VerifyMismatchError:
        return False


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_aware_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; Postgres keeps it. Normalize to aware-UTC
    so comparisons work the same against either backend."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def new_expiration() -> datetime:
    return now_utc() + SESSION_DURATION


def needs_renewal(expira_em: datetime) -> bool:
    return as_aware_utc(expira_em) - now_utc() < SESSION_RENEW_THRESHOLD
