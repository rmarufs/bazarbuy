import asyncio
from typing import cast

import pytest
from httpx import AsyncClient, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PLACEHOLDER_SECRET_KEY, Settings
from app.core.security import SESSION_COOKIE_NAME, hash_password, verify_password
from app.models import Admin, Setting
from app.services import auth_service
from app.services.auth_service import (
    LOGIN_BLOCK_SECONDS,
    LOGIN_WINDOW_SECONDS,
    MAX_LOGIN_ATTEMPTS,
    LoginRateLimiter,
    TooManyLoginAttemptsError,
)

USERNAME = "owner"
PASSWORD = "secret-pass"


async def login(client: AsyncClient, password: str = PASSWORD) -> Response:
    return await client.post(
        "/admin/login",
        data={"username": USERNAME, "password": password},
        follow_redirects=False,
    )


async def test_settings_requires_login(client: AsyncClient) -> None:
    response = await client.get("/admin/settings", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


async def test_login_with_wrong_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await auth_service.upsert_admin(db_session, USERNAME, PASSWORD)

    response = await login(client, "wrong")

    assert response.status_code == 401
    assert "Неверный логин или пароль" in response.text
    assert SESSION_COOKIE_NAME not in response.headers.get("set-cookie", "")


async def test_login_success_sets_httponly_cookie(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await auth_service.upsert_admin(db_session, USERNAME, PASSWORD)

    response = await login(client)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/products"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie


async def test_admin_can_read_and_update_whatsapp_number(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await auth_service.upsert_admin(db_session, USERNAME, PASSWORD)
    await login(client)

    page = await client.get("/admin/settings")
    assert page.status_code == 200
    assert 'name="whatsapp_number"' in page.text

    response = await client.post(
        "/admin/settings",
        data={"whatsapp_number": " +992 90 123-45-67 "},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/settings?saved=1"

    saved_page = await client.get("/admin/settings?saved=1")
    assert "Сохранено" in saved_page.text
    assert "+992901234567" in saved_page.text
    db_session.expire_all()
    setting = (await db_session.execute(select(Setting))).scalar_one()
    assert setting.whatsapp_number == "+992901234567"


async def test_invalid_whatsapp_number_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await auth_service.upsert_admin(db_session, USERNAME, PASSWORD)
    await login(client)

    response = await client.post(
        "/admin/settings", data={"whatsapp_number": "abc"}, follow_redirects=False
    )

    assert response.status_code == 400
    assert "Введите номер" in response.text


async def test_logout_closes_settings(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await auth_service.upsert_admin(db_session, USERNAME, PASSWORD)
    await login(client)

    response = await client.post("/admin/logout", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"

    after = await client.get("/admin/settings", follow_redirects=False)
    assert after.status_code == 303
    assert after.headers["location"] == "/admin/login"


async def test_upsert_admin_creates_then_updates_password(
    db_session: AsyncSession,
) -> None:
    created = await auth_service.upsert_admin(db_session, USERNAME, "first-pass")
    assert created.password_hash != "first-pass"
    assert await auth_service.authenticate(db_session, USERNAME, "first-pass")

    await auth_service.upsert_admin(db_session, USERNAME, "second-pass")

    admins = (await db_session.execute(select(Admin))).scalars().all()
    assert len(admins) == 1
    assert await auth_service.authenticate(db_session, USERNAME, "first-pass") is None
    assert await auth_service.authenticate(db_session, USERNAME, "second-pass")


def test_password_hash_and_verify() -> None:
    hashed = hash_password(PASSWORD)
    assert hashed.startswith("$2b$")
    assert verify_password(PASSWORD, hashed) is True
    assert verify_password("wrong-pass", hashed) is False
    assert verify_password(PASSWORD, "not-a-valid-bcrypt-hash") is False


def test_password_longer_than_72_bytes_is_truncated() -> None:
    long_password = "a" * 80
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed) is True
    assert verify_password("a" * 72 + "b" * 8, hashed) is True
    assert verify_password("a" * 71 + "b", hashed) is False


def test_verify_password_accepts_existing_passlib_hash() -> None:
    passlib_hash = "$2b$12$z9j44sGVkd5HsJ5Gj3PIAeOFhZg5gO5LbkudbHuZ61z3OQl9gX3Fq"
    assert verify_password("secret-pass", passlib_hash) is True
    assert verify_password("wrong-pass", passlib_hash) is False


def test_login_rate_limiter_blocks_unblocks_and_resets() -> None:
    now = 1000.0
    limiter = LoginRateLimiter(clock=lambda: now)

    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        limiter.check_and_register("10.0.0.1")

    # Successful login resets accumulated attempts.
    limiter.reset("10.0.0.1")
    for _ in range(MAX_LOGIN_ATTEMPTS - 1):
        limiter.check_and_register("10.0.0.1")

    # 5th attempt in the window is allowed and sets the 15-minute block.
    limiter.check_and_register("10.0.0.1")
    with pytest.raises(TooManyLoginAttemptsError):
        limiter.check_and_register("10.0.0.1")
    limiter.check_and_register("10.0.0.2")
    limiter.reset("10.0.0.2")

    # Still blocked just before block_seconds elapses.
    now += LOGIN_BLOCK_SECONDS - 1
    with pytest.raises(TooManyLoginAttemptsError):
        limiter.check_and_register("10.0.0.1")

    # Unblocked once block_seconds elapses, and expired entries are pruned.
    limiter.check_and_register("10.0.0.3")
    now += LOGIN_WINDOW_SECONDS + 1
    limiter.reset("10.0.0.1")
    assert limiter._records == {}
    limiter.check_and_register("10.0.0.1")


def test_login_rate_limiter_twenty_calls_allow_only_five() -> None:
    limiter = LoginRateLimiter()
    allowed = 0
    blocked = 0

    for _ in range(20):
        try:
            limiter.check_and_register("10.0.0.1")
            allowed += 1
        except TooManyLoginAttemptsError:
            blocked += 1

    assert allowed == MAX_LOGIN_ATTEMPTS
    assert blocked == 20 - MAX_LOGIN_ATTEMPTS


async def test_login_admin_concurrency_allows_only_five_authentications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_calls = 0

    async def slow_authenticate(
        session: AsyncSession, username: str, password: str
    ) -> Admin | None:
        nonlocal auth_calls
        auth_calls += 1
        await asyncio.sleep(0)
        return None

    monkeypatch.setattr(auth_service, "authenticate", slow_authenticate)
    dummy_session = cast(AsyncSession, object())

    results = await asyncio.gather(
        *(
            auth_service.login_admin(dummy_session, USERNAME, "wrong", "10.0.0.1")
            for _ in range(20)
        ),
        return_exceptions=True,
    )

    assert auth_calls == MAX_LOGIN_ATTEMPTS
    assert sum(r is None for r in results) == MAX_LOGIN_ATTEMPTS
    assert sum(isinstance(r, TooManyLoginAttemptsError) for r in results) == (
        20 - MAX_LOGIN_ATTEMPTS
    )


async def test_login_blocks_after_five_failed_attempts_even_with_valid_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await auth_service.upsert_admin(db_session, USERNAME, PASSWORD)

    for _ in range(MAX_LOGIN_ATTEMPTS):
        wrong = await login(client, "wrong-password")
        assert wrong.status_code == 401

    blocked = await login(client, PASSWORD)
    assert blocked.status_code == 429
    assert "Слишком много попыток входа. Попробуйте позже." in blocked.text
    assert SESSION_COOKIE_NAME not in blocked.headers.get("set-cookie", "")


async def test_authenticate_unknown_username_still_verifies_password(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[str, str]] = []
    real_verify = auth_service.verify_password

    def spy_verify(password: str, password_hash: str) -> bool:
        calls.append((password, password_hash))
        return real_verify(password, password_hash)

    monkeypatch.setattr(auth_service, "verify_password", spy_verify)

    result = await auth_service.authenticate(db_session, "unknown-admin", "some-pass")

    assert result is None
    assert len(calls) == 1
    assert calls[0][0] == "some-pass"
    assert calls[0][1].startswith("$2b$")


def test_settings_rejects_weak_or_placeholder_secret_key_in_production() -> None:
    db_url = "postgresql+asyncpg://u:p@localhost:5432/db"

    with pytest.raises(ValidationError, match="placeholder"):
        Settings(
            _env_file=None,
            DATABASE_URL=db_url,
            SECRET_KEY=PLACEHOLDER_SECRET_KEY,
            APP_ENV="production",
        )

    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(
            _env_file=None,
            DATABASE_URL=db_url,
            SECRET_KEY="short-secret-key",
            APP_ENV="production",
        )

    prod = Settings(
        _env_file=None,
        DATABASE_URL=db_url,
        SECRET_KEY="s" * 32,
        APP_ENV="production",
    )
    assert prod.APP_ENV == "production"

    dev = Settings(
        _env_file=None,
        DATABASE_URL=db_url,
        SECRET_KEY=PLACEHOLDER_SECRET_KEY,
        APP_ENV="development",
    )
    assert dev.APP_ENV == "development"
