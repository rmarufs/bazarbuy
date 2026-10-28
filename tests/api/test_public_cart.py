from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Product, ProductImage
from app.schemas.product import normalize_search_name
from app.services import setting_service


async def add_category(session: AsyncSession, name: str) -> Category:
    category = Category(name=name)
    session.add(category)
    await session.commit()
    return category


async def add_product(
    session: AsyncSession,
    category: Category,
    name: str,
    price: int = 250,
    images: tuple[str, ...] = (),
) -> Product:
    product = Product(
        name=name,
        description="",
        price=price,
        category_id=category.id,
        position=0,
        search_name=normalize_search_name(name),
    )
    session.add(product)
    await session.flush()
    session.add_all(
        ProductImage(product_id=product.id, file_path=path, position=index)
        for index, path in enumerate(images)
    )
    await session.commit()
    return product


async def test_cart_page_renders_with_whatsapp_number(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await setting_service.update_whatsapp_number(db_session, "+992 900 11-22-33")

    response = await client.get("/cart")

    assert response.status_code == 200
    page = response.text
    assert 'id="cart-container"' in page
    assert 'data-whatsapp-number="+992900112233"' in page
    assert 'data-whatsapp-url="https://wa.me/992900112233"' in page
    assert 'id="whatsapp-order-btn"' in page
    assert "Заказать в WhatsApp" in page
    assert "Номер WhatsApp для заказов временно не указан" not in page
    assert "/static/js/cart.js" in page
    assert (await client.get("/static/js/cart.js")).status_code == 200


async def test_cart_page_without_whatsapp_number_disables_order_button(
    client: AsyncClient,
) -> None:
    response = await client.get("/cart")

    assert response.status_code == 200
    page = response.text
    assert 'id="cart-container"' in page
    assert 'data-whatsapp-number=""' in page
    assert 'data-whatsapp-url=""' in page
    assert 'id="whatsapp-order-btn"' in page
    assert "disabled" in page
    assert "Номер WhatsApp для заказов временно не указан" in page


async def test_api_cart_items_returns_existing_products_and_ignores_missing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    first = await add_product(
        db_session,
        category,
        "Сумка кожаная",
        price=350,
        images=("bag1.jpg", "bag2.jpg"),
    )
    second = await add_product(
        db_session,
        category,
        "Кошелёк",
        price=120,
    )

    response = await client.get(
        "/api/cart-items",
        params={"ids": f"{second.id},999999,{first.id},{second.id}"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": second.id,
            "name": "Кошелёк",
            "price": 120,
            "image_url": "",
            "url": f"/products/{second.id}",
        },
        {
            "id": first.id,
            "name": "Сумка кожаная",
            "price": 350,
            "image_url": "/uploads/bag1.jpg",
            "url": f"/products/{first.id}",
        },
    ]


async def test_api_cart_items_handles_empty_or_invalid_ids(
    client: AsyncClient,
) -> None:
    for raw_ids in ("", "   ", "abc,-5,0"):
        response = await client.get("/api/cart-items", params={"ids": raw_ids})
        assert response.status_code == 200
        assert response.json() == []

    no_param_response = await client.get("/api/cart-items")
    assert no_param_response.status_code == 200
    assert no_param_response.json() == []
