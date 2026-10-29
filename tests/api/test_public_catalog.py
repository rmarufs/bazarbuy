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
    position: int = 0,
    price: int = 250,
    description: str = "",
    images: tuple[str, ...] = (),
) -> Product:
    product = Product(
        name=name,
        description=description,
        price=price,
        category_id=category.id,
        position=position,
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


def card_names(html: str) -> list[str]:
    """Names of the product cards, in page order."""
    marker = '<h2 class="product-card-title">'
    return [part.split("</h2>")[0] for part in html.split(marker)[1:]]


async def test_catalog_lists_products_by_position(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    await add_product(db_session, category, "Товар A", position=2)
    await add_product(db_session, category, "Товар B", position=0)
    await add_product(db_session, category, "Товар C", position=1)

    response = await client.get("/")

    assert response.status_code == 200
    assert card_names(response.text) == ["Товар B", "Товар C", "Товар A"]
    assert "250 сомони" in response.text
    assert 'data-product-name="Товар B"' in response.text
    assert 'data-product-price="250"' in response.text


async def test_catalog_card_shows_first_photo_and_cart_data(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    first_url = (
        "https://res.cloudinary.com/demo/image/upload/v1/bazarbuy/products/first.jpg"
    )
    second_url = (
        "https://res.cloudinary.com/demo/image/upload/v1/bazarbuy/products/second.jpg"
    )
    product = await add_product(
        db_session, category, "Сумка", images=(first_url, second_url)
    )

    page = (await client.get("/")).text

    assert f'src="{first_url}"' in page
    assert "second.jpg" not in page
    assert f'data-product-image="{first_url}"' in page
    assert f'data-product-id="{product.id}"' in page
    assert f'href="/products/{product.id}"' in page


async def test_empty_catalog_shows_not_found_block(client: AsyncClient) -> None:
    response = await client.get("/", params={"q": "ничего"})
    assert response.status_code == 200
    assert "Ничего не найдено" in response.text
    assert "Сбросить фильтры" in response.text


async def test_filter_by_category(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    bags = await add_category(db_session, "Сумки")
    shoes = await add_category(db_session, "Обувь")
    await add_product(db_session, bags, "Сумка 1", position=0)
    await add_product(db_session, shoes, "Туфли 1", position=1)
    await add_product(db_session, bags, "Сумка 2", position=2)

    response = await client.get("/", params={"category_id": bags.id})

    assert response.status_code == 200
    assert card_names(response.text) == ["Сумка 1", "Сумка 2"]
    assert 'class="chip active"' in response.text


async def test_category_chips_link_to_filters(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    bags = await add_category(db_session, "Сумки")
    await add_category(db_session, "Пустая категория")
    await add_product(db_session, bags, "Сумка")

    page = (await client.get("/")).text

    assert "Все категории" in page
    assert f"/?category_id={bags.id}" in page
    assert "Пустая категория" not in page


async def test_search_ignores_case_and_spaces(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    await add_product(db_session, category, "Сумка Louis Vuitton", position=0)
    await add_product(db_session, category, "Часы Casio", position=1)

    for query in ("Louis Vuitton", "louis vuitton", "LOUISVUITTON", "  Vuit ton "):
        response = await client.get("/", params={"q": query})
        assert response.status_code == 200
        assert card_names(response.text) == ["Сумка Louis Vuitton"], query

    response = await client.get("/", params={"q": "СУМКА louis"})
    assert card_names(response.text) == ["Сумка Louis Vuitton"]


async def test_search_keeps_query_in_input(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    await add_product(db_session, category, "Сумка Louis Vuitton")

    page = (await client.get("/", params={"q": "Louis Vuitton"})).text

    assert 'value="Louis Vuitton"' in page
    assert "Сбросить поиск" in page


async def test_search_treats_wildcards_literally(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    await add_product(db_session, category, "Сумка")

    for query in ("%", "_"):
        response = await client.get("/", params={"q": query})
        assert card_names(response.text) == [], query


async def test_blank_search_returns_everything(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    await add_product(db_session, category, "Сумка", position=0)
    await add_product(db_session, category, "Часы", position=1)

    response = await client.get("/", params={"q": "   "})

    assert card_names(response.text) == ["Сумка", "Часы"]


async def test_category_filter_and_search_work_together(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    bags = await add_category(db_session, "Сумки")
    wallets = await add_category(db_session, "Кошельки")
    await add_product(db_session, bags, "Сумка Louis Vuitton", position=0)
    await add_product(db_session, wallets, "Кошелёк Louis Vuitton", position=1)
    await add_product(db_session, bags, "Сумка Gucci", position=2)

    response = await client.get(
        "/", params={"category_id": bags.id, "q": "louis vuitton"}
    )

    assert card_names(response.text) == ["Сумка Louis Vuitton"]
    assert f'name="category_id" value="{bags.id}"' in response.text


async def test_product_page_shows_details_and_all_photos(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    photos = tuple(
        f"https://res.cloudinary.com/demo/image/upload/v1/bazarbuy/products/photo{index}.jpg"
        for index in range(5)
    )
    product = await add_product(
        db_session,
        category,
        "Сумка <b>Louis</b>",
        price=1250,
        description="Кожаная сумка.\nПривезём под заказ.",
        images=photos,
    )

    response = await client.get(f"/products/{product.id}")

    assert response.status_code == 200
    page = response.text
    assert "Сумка &lt;b&gt;Louis&lt;/b&gt;" in page  # autoescape stays on
    assert "<b>Louis</b>" not in page
    assert "Кожаная сумка." in page
    assert "Привезём под заказ." in page
    assert "1250 сомони" in page
    assert "Товар под предзаказ" in page
    assert "Сумки" in page
    assert "Назад в каталог" in page
    for photo in photos:
        assert page.count(photo) >= 1
    assert page.count("data-gallery-thumb") == 5
    assert f'id="gallery-main-image" src="{photos[0]}"' in page
    assert f'data-product-id="{product.id}"' in page
    assert "/static/js/public_product.js" in page
    assert (await client.get("/static/js/public_product.js")).status_code == 200


async def test_product_page_without_photos_has_placeholder(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session, "Сумки")
    product = await add_product(db_session, category, "Сумка")

    response = await client.get(f"/products/{product.id}")

    assert response.status_code == 200
    assert "gallery-main-image" not in response.text
    assert "data-gallery-thumb" not in response.text


async def test_unknown_product_returns_404_page(client: AsyncClient) -> None:
    response = await client.get("/products/999")

    assert response.status_code == 404
    assert "Страница не найдена" in response.text
    assert "Назад в каталог" in response.text


async def test_about_page(client: AsyncClient) -> None:
    response = await client.get("/about")

    assert response.status_code == 200
    assert "предзаказ" in response.text
    assert "WhatsApp" in response.text


async def test_contacts_page_shows_whatsapp_number(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await setting_service.update_whatsapp_number(db_session, "+992 900 11-22-33")

    response = await client.get("/contacts")

    assert response.status_code == 200
    assert "+992900112233" in response.text
    assert 'href="https://wa.me/992900112233"' in response.text
    assert "Написать в WhatsApp" in response.text


async def test_contacts_page_without_number(client: AsyncClient) -> None:
    response = await client.get("/contacts")

    assert response.status_code == 200
    assert "wa.me" not in response.text
    assert "Номер WhatsApp пока не указан" in response.text


async def test_public_pages_share_header_with_cart_placeholder(
    client: AsyncClient,
) -> None:
    for url in ("/", "/about", "/contacts"):
        page = (await client.get(url)).text
        assert "Bazarbuy.tj" in page
        assert 'href="/about"' in page
        assert 'href="/contacts"' in page
        assert "data-cart-count" in page
