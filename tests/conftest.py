from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.services import auth_service


@pytest.fixture(autouse=True)
def upload_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point UPLOAD_DIR to a temporary folder so tests never touch real uploads."""
    directory = tmp_path / "uploads"
    directory.mkdir()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(directory))
    return directory


def get_test_database_url() -> str:
    """Validate and return the test database URL, or skip if not configured."""
    url = settings.TEST_DATABASE_URL
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; set it in .env to run DB tests")
    assert url != settings.DATABASE_URL, (
        "TEST_DATABASE_URL must differ from DATABASE_URL"
    )
    return url


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Async session bound to the test database.

    Tables are created before each test and dropped after it,
    so every test starts with an empty schema.
    """
    engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP client talking to the app, using the test DB session."""

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def admin_client(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    """HTTP client already signed in as an admin."""
    await auth_service.upsert_admin(db_session, "owner", "secret-pass")
    await client.post(
        "/admin/login", data={"username": "owner", "password": "secret-pass"}
    )
    yield client
