from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Product

NOT_EMPTY_MESSAGE = "Нельзя удалить категорию, пока в ней есть товары"
DUPLICATE_MESSAGE = "Категория с таким названием уже существует"


async def add_category(session: AsyncSession, name: str) -> Category:
    category = Category(name=name)
    session.add(category)
    await session.commit()
    return category


async def get_names(session: AsyncSession) -> list[str]:
    session.expire_all()
    result = await session.execute(select(Category.name).order_by(Category.name))
    return list(result.scalars().all())


async def test_categories_require_login(client: AsyncClient) -> None:
    response = await client.get("/admin/categories", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"

    response = await client.post(
        "/admin/categories", data={"name": "Bags"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/login"


async def test_create_category_appears_in_list(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await admin_client.post(
        "/admin/categories", data={"name": "  Сумки  "}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/categories"

    page = await admin_client.get("/admin/categories")
    assert page.status_code == 200
    assert "Сумки" in page.text
    assert "0 товаров" in page.text
    assert await get_names(db_session) == ["Сумки"]


async def test_create_category_with_empty_name_fails(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await admin_client.post("/admin/categories", data={"name": "   "})

    assert response.status_code == 400
    assert "Название должно содержать от 1 до 100 символов" in response.text
    assert await get_names(db_session) == []


async def test_create_category_with_too_long_name_fails(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post("/admin/categories", data={"name": "a" * 101})
    assert response.status_code == 400


async def test_create_duplicate_category_fails_ignoring_case(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_category(db_session, "Сумки")

    response = await admin_client.post("/admin/categories", data={"name": "сумки"})

    assert response.status_code == 400
    assert DUPLICATE_MESSAGE in response.text
    assert await get_names(db_session) == ["Сумки"]


async def test_rename_category(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")

    response = await admin_client.post(
        f"/admin/categories/{category.id}/rename",
        data={"name": "Рюкзаки"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert await get_names(db_session) == ["Рюкзаки"]


async def test_rename_to_existing_name_fails(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_category(db_session, "Сумки")
    other = await add_category(db_session, "Обувь")

    response = await admin_client.post(
        f"/admin/categories/{other.id}/rename", data={"name": "СУМКИ"}
    )

    assert response.status_code == 400
    assert DUPLICATE_MESSAGE in response.text
    assert await get_names(db_session) == ["Обувь", "Сумки"]


async def test_rename_unknown_category_returns_404(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/admin/categories/999/rename", data={"name": "X"}
    )
    assert response.status_code == 404


async def test_delete_empty_category(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")

    response = await admin_client.post(
        f"/admin/categories/{category.id}/delete", follow_redirects=False
    )

    assert response.status_code == 303
    assert await get_names(db_session) == []


async def test_delete_category_with_products_is_blocked(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    db_session.add(
        Product(name="Bag", price=100, search_name="bag", category_id=category.id)
    )
    await db_session.commit()

    response = await admin_client.post(f"/admin/categories/{category.id}/delete")

    assert response.status_code == 400
    assert NOT_EMPTY_MESSAGE in response.text
    assert "1 товар" in response.text
    assert await get_names(db_session) == ["Сумки"]
