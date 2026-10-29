import asyncio
import io
import os
import socket
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image
from playwright.sync_api import Page
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.services import (
    auth_service,
    category_service,
    product_service,
    setting_service,
)
from tests.conftest import get_test_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = Path(__file__).parent / "screenshots"
VIEWPORT = {"width": 390, "height": 844}  # mobile first, see docs/SPEC.md
ADMIN_USERNAME = "owner"
ADMIN_PASSWORD = "secret-pass"
CATEGORY_NAME = "Сумки"
SECOND_CATEGORY_NAME = "Обувь"
WHATSAPP_NUMBER = "+992900112233"
SERVER_START_TIMEOUT = 20.0


class LiveServer:
    """A running app instance that works only with the test database."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def url(self, path: str) -> str:
        return f"{self.base_url}{path}"


def make_image(image_format: str = "JPEG", color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format=image_format)
    return buffer.getvalue()


def run_async[T](coroutine_factory: Callable[[], Awaitable[T]]) -> T:
    """Run async code in its own thread and loop.

    Playwright's sync API keeps an event loop alive in the main thread, so
    `asyncio.run` cannot be called there directly.
    """

    async def runner() -> T:
        return await coroutine_factory()

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, runner()).result()


def run_with_session[T](action: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run `action` with a session bound to the test database."""

    async def factory() -> T:
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        try:
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            async with sessions() as session:
                return await action(session)
        finally:
            await engine.dispose()

    return run_async(factory)


def reset_schema(create: bool) -> None:
    """Drop all tables of the test database and optionally create them again."""

    async def factory() -> None:
        engine = create_async_engine(get_test_database_url(), poolclass=NullPool)
        try:
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.drop_all)
                if create:
                    await connection.run_sync(Base.metadata.create_all)
        finally:
            await engine.dispose()

    run_async(factory)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(
    base_url: str, process: subprocess.Popen[bytes], log: Path
) -> None:
    deadline = time.monotonic() + SERVER_START_TIMEOUT
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Server exited early:\n{log.read_text()}")
        try:
            if httpx.get(f"{base_url}/health", timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"Server did not start in time:\n{log.read_text()}")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    return {**browser_context_args, "viewport": VIEWPORT, "locale": "ru-RU"}


@pytest.fixture
def database() -> Iterator[None]:
    """Empty test database with one admin; dropped after the test."""
    get_test_database_url()
    reset_schema(create=True)
    run_with_session(
        lambda session: auth_service.upsert_admin(
            session, ADMIN_USERNAME, ADMIN_PASSWORD
        )
    )
    yield
    reset_schema(create=False)


@pytest.fixture
def live_server(
    database: None, upload_dir: Path, tmp_path: Path
) -> Iterator[LiveServer]:
    """Real uvicorn server using the test database and the temporary upload dir."""
    port = free_port()
    environment = os.environ | {
        "DATABASE_URL": get_test_database_url(),
        "UPLOAD_DIR": str(upload_dir),
    }
    log_path = tmp_path / "server.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        base_url = f"http://127.0.0.1:{port}"
        try:
            wait_until_ready(base_url, process, log_path)
            yield LiveServer(base_url)
        finally:
            process.terminate()
            process.wait(timeout=10)


@pytest.fixture
def seed_products(database: None) -> Callable[[list[str]], None]:
    """Create the category and products directly in the DB.

    The last name in the list ends up first on the page (newest on top).
    """

    def seed(names: list[str]) -> None:
        async def action(session: AsyncSession) -> None:
            await setting_service.update_whatsapp_number(session, WHATSAPP_NUMBER)
            category = await category_service.create_category(session, CATEGORY_NAME)
            photos = [
                make_image("JPEG", "red"),
                make_image("JPEG", "green"),
                make_image("JPEG", "blue"),
            ]
            for index, name in enumerate(names):
                await product_service.create_product(
                    session,
                    name,
                    f"Описание для {name}",
                    100 + index,
                    category.id,
                    photos if index == len(names) - 1 else [photos[0]],
                )

        run_with_session(action)

    return seed


@pytest.fixture
def seed_public_catalog(database: None) -> Callable[[], dict[str, int]]:
    """Seed two categories, products with multiple photos, and WhatsApp settings."""

    def seed() -> dict[str, int]:
        async def action(session: AsyncSession) -> dict[str, int]:
            await setting_service.update_whatsapp_number(session, WHATSAPP_NUMBER)
            bags = await category_service.create_category(session, CATEGORY_NAME)
            shoes = await category_service.create_category(
                session, SECOND_CATEGORY_NAME
            )
            sneakers = await product_service.create_product(
                session,
                "Кроссовки Nike",
                "Удобные кроссовки под предзаказ.",
                400,
                shoes.id,
                [make_image("JPEG", "navy")],
            )
            bag = await product_service.create_product(
                session,
                "Сумка Louis Vuitton",
                "Кожаная сумка премиум-класса под предзаказ.",
                250,
                bags.id,
                [
                    make_image("JPEG", "red"),
                    make_image("JPEG", "green"),
                    make_image("JPEG", "blue"),
                ],
            )
            return {"bag_id": bag.id, "sneakers_id": sneakers.id}

        return run_with_session(action)

    return seed


@pytest.fixture
def admin_page(page: Page, live_server: LiveServer) -> Page:
    """Browser page already signed in to the admin area."""
    page.goto(live_server.url("/admin/login"))
    page.fill("#username", ADMIN_USERNAME)
    page.fill("#password", ADMIN_PASSWORD)
    page.get_by_role("button", name="Войти").click()
    page.wait_for_url("**/admin/products")
    return page


def save_screenshot(page: Page, name: str) -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SCREENSHOT_DIR / name), full_page=True)
