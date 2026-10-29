import time
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import Admin

MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_BLOCK_SECONDS = 15 * 60
TOO_MANY_ATTEMPTS_MESSAGE = "Слишком много попыток входа. Попробуйте позже."

# Precomputed once at import time so unknown usernames still run a full bcrypt check.
_DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing-mitigation")


class TooManyLoginAttemptsError(Exception):
    """Raised when an IP address is temporarily blocked after repeated failed logins."""

    def __init__(self, message: str = TOO_MANY_ATTEMPTS_MESSAGE) -> None:
        super().__init__(message)


@dataclass
class _AttemptRecord:
    failures: list[float] = field(default_factory=list)
    blocked_until: float | None = None


class LoginRateLimiter:
    """In-memory per-IP login attempt limiter with a replaceable clock."""

    def __init__(
        self,
        max_attempts: int = MAX_LOGIN_ATTEMPTS,
        window_seconds: float = LOGIN_WINDOW_SECONDS,
        block_seconds: float = LOGIN_BLOCK_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._block_seconds = block_seconds
        self._clock = clock
        self._records: dict[str, _AttemptRecord] = {}

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        expired_keys: list[str] = []
        for key, record in self._records.items():
            if record.blocked_until is not None and now >= record.blocked_until:
                record.blocked_until = None
            record.failures = [ts for ts in record.failures if ts > cutoff]
            if record.blocked_until is None and not record.failures:
                expired_keys.append(key)
        for key in expired_keys:
            del self._records[key]

    def is_blocked(self, key: str) -> bool:
        now = self._clock()
        self._prune(now)
        record = self._records.get(key)
        return record is not None and record.blocked_until is not None

    def record_failure(self, key: str) -> None:
        now = self._clock()
        self._prune(now)
        record = self._records.setdefault(key, _AttemptRecord())
        if record.blocked_until is not None:
            return
        record.failures.append(now)
        if len(record.failures) >= self._max_attempts:
            record.blocked_until = now + self._block_seconds
            record.failures.clear()

    def reset(self, key: str) -> None:
        now = self._clock()
        self._prune(now)
        self._records.pop(key, None)

    def clear(self) -> None:
        self._records.clear()


login_rate_limiter = LoginRateLimiter()


async def get_admin_by_username(session: AsyncSession, username: str) -> Admin | None:
    result = await session.execute(select(Admin).where(Admin.username == username))
    return result.scalar_one_or_none()


async def authenticate(
    session: AsyncSession, username: str, password: str
) -> Admin | None:
    """Return the admin if the credentials are correct, otherwise None."""
    admin = await get_admin_by_username(session, username)
    if admin is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, admin.password_hash):
        return None
    return admin


async def login_admin(
    session: AsyncSession,
    username: str,
    password: str,
    client_ip: str,
    limiter: LoginRateLimiter | None = None,
) -> Admin | None:
    """Authenticate an admin while enforcing per-IP login rate limits."""
    active_limiter = limiter if limiter is not None else login_rate_limiter
    if active_limiter.is_blocked(client_ip):
        raise TooManyLoginAttemptsError()
    admin = await authenticate(session, username, password)
    if admin is None:
        active_limiter.record_failure(client_ip)
        return None
    active_limiter.reset(client_ip)
    return admin


async def upsert_admin(session: AsyncSession, username: str, password: str) -> Admin:
    """Create the admin, or update the password if the username already exists."""
    admin = await get_admin_by_username(session, username)
    if admin is None:
        admin = Admin(username=username, password_hash=hash_password(password))
        session.add(admin)
    else:
        admin.password_hash = hash_password(password)
    await session.commit()
    return admin
