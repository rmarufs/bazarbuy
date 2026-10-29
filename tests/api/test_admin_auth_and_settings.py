from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import SESSION_COOKIE_NAME, hash_password, verify_password
from app.models import Admin, Setting
from app.services import auth_service

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
