import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient, Response
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Category, Product, ProductImage
from app.services import image_service, product_service

FileField = tuple[str, tuple[str, bytes, str]]

TOO_MANY_MESSAGE = "У товара может быть не более 5 фотографий"
INVALID_IMAGE_MESSAGE = "Допустимы только изображения JPEG, PNG или WEBP"
TOO_BIG_MESSAGE = "Размер фотографии не должен превышать 5 МБ"


def make_image(image_format: str = "JPEG", color: str = "red") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), color).save(buffer, format=image_format)
    return buffer.getvalue()


def photo(index: int, color: str = "red") -> FileField:
    return ("photos", (f"photo{index}.jpg", make_image("JPEG", color), "image/jpeg"))


async def add_category(session: AsyncSession, name: str = "Сумки") -> Category:
    category = Category(name=name)
    session.add(category)
    await session.commit()
    return category


def product_data(category: Category, **overrides: str) -> dict[str, str]:
    data = {
        "name": "Louis Vuitton",
        "description": "Описание",
        "price": "250",
        "category_id": str(category.id),
    }
    return data | overrides


async def create_via_post(
    client: AsyncClient,
    category: Category,
    files: list[FileField] | None = None,
    **overrides: str,
) -> None:
    response = await client.post(
        "/admin/products/new",
        data=product_data(category, **overrides),
        files=files or [],
        follow_redirects=False,
    )
    assert response.status_code == 303


async def only_product(session: AsyncSession) -> Product:
    products = await product_service.list_products(session)
    assert len(products) == 1
    return products[0]


async def count_rows(session: AsyncSession, model: type) -> int:
    session.expire_all()
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_products_require_login(client: AsyncClient) -> None:
    for method, url in [
        ("GET", "/admin/products"),
        ("GET", "/admin/products/new"),
        ("POST", "/admin/products/new"),
        ("GET", "/admin/products/1/edit"),
        ("POST", "/admin/products/1/edit"),
        ("POST", "/admin/products/1/delete"),
        ("POST", "/admin/products/bulk-delete"),
        ("POST", "/admin/products/reorder"),
    ]:
        response = await client.request(method, url, follow_redirects=False)
        assert response.status_code == 303, url
        assert response.headers["location"] == "/admin/login", url


async def test_admin_index_redirects_to_products(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/admin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/products"


async def test_new_page_without_categories_shows_hint(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/admin/products/new")
    assert response.status_code == 200
    assert 'href="/admin/categories"' in response.text
    assert "<select" not in response.text


async def test_new_page_lists_categories(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    await add_category(db_session, "Сумки")
    response = await admin_client.get("/admin/products/new")
    assert "<select" in response.text
    assert "Сумки" in response.text


async def test_create_product_with_two_images(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    cloudinary_storage: set[str],
) -> None:
    category = await add_category(db_session)
    files = [
        photo(1, "red"),
        ("photos", ("two.png", make_image("PNG", "blue"), "image/png")),
    ]

    await create_via_post(
        admin_client, category, files, name="  Louis Vuitton  ", price="250"
    )

    product = await only_product(db_session)
    assert product.name == "Louis Vuitton"
    assert product.search_name == "louisvuitton"
    assert product.price == 250
    assert product.category.name == "Сумки"
    assert [image.position for image in product.images] == [0, 1]
    urls = [image.file_path for image in product.images]
    assert urls[0].startswith("https://") and urls[0].endswith(".jpg")
    assert urls[1].startswith("https://") and urls[1].endswith(".png")
    assert cloudinary_storage == set(urls)

    page = await admin_client.get("/admin/products")
    assert "Louis Vuitton" in page.text
    assert "250 сомони" in page.text
    assert "Сумки" in page.text
    assert f'src="{urls[0]}"' in page.text


async def test_create_product_without_images(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)

    await create_via_post(admin_client, category)

    assert (await only_product(db_session)).images == []
    page = await admin_client.get("/admin/products")
    assert "Louis Vuitton" in page.text


async def test_new_product_goes_first(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)

    await create_via_post(admin_client, category, name="First")
    await create_via_post(admin_client, category, name="Second")
    await create_via_post(admin_client, category, name="Third")

    products = await product_service.list_products(db_session)
    assert [product.name for product in products] == ["Third", "Second", "First"]
    assert products[0].position < products[1].position < products[2].position


async def test_more_than_five_images_is_rejected(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    cloudinary_storage: set[str],
) -> None:
    category = await add_category(db_session)

    response = await admin_client.post(
        "/admin/products/new",
        data=product_data(category),
        files=[photo(index) for index in range(6)],
    )

    assert response.status_code == 400
    assert TOO_MANY_MESSAGE in response.text
    assert await count_rows(db_session, Product) == 0
    assert cloudinary_storage == set()


async def test_fake_image_is_rejected(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    cloudinary_storage: set[str],
) -> None:
    category = await add_category(db_session)
    fake = ("photos", ("script.jpg", b"print('not an image')", "image/jpeg"))

    response = await admin_client.post(
        "/admin/products/new",
        data=product_data(category),
        files=[photo(1), fake],
    )

    assert response.status_code == 400
    assert INVALID_IMAGE_MESSAGE in response.text
    assert await count_rows(db_session, Product) == 0
    assert cloudinary_storage == set()


async def test_unsupported_image_format_is_rejected(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    gif = ("photos", ("anim.gif", make_image("GIF"), "image/gif"))

    response = await admin_client.post(
        "/admin/products/new", data=product_data(category), files=[gif]
    )

    assert response.status_code == 400
    assert INVALID_IMAGE_MESSAGE in response.text


async def test_oversized_image_is_rejected(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    big = (
        "photos",
        ("big.jpg", b"0" * (image_service.MAX_IMAGE_BYTES + 1), "image/jpeg"),
    )

    response = await admin_client.post(
        "/admin/products/new", data=product_data(category), files=[big]
    )

    assert response.status_code == 400
    assert TOO_BIG_MESSAGE in response.text


async def test_invalid_fields_are_rejected(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    cases = {
        "name": ("   ", "Название должно содержать от 1 до 200 символов"),
        "price": ("0", "Цена должна быть целым числом больше 0"),
    }
    for field, (value, message) in cases.items():
        response = await admin_client.post(
            "/admin/products/new", data=product_data(category, **{field: value})
        )
        assert response.status_code == 400
        assert message in response.text

    for price in ("abc", "12.5", "-5", ""):
        response = await admin_client.post(
            "/admin/products/new", data=product_data(category, price=price)
        )
        assert response.status_code == 400

    response = await admin_client.post(
        "/admin/products/new", data=product_data(category, category_id="")
    )
    assert response.status_code == 400
    assert "Выберите категорию" in response.text

    response = await admin_client.post(
        "/admin/products/new", data=product_data(category, category_id="9999")
    )
    assert response.status_code == 400
    assert "Выбранная категория не найдена" in response.text
    assert await count_rows(db_session, Product) == 0


async def test_error_keeps_entered_values(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)

    response = await admin_client.post(
        "/admin/products/new",
        data=product_data(category, name="Keep me", price="0"),
    )

    assert response.status_code == 400
    assert 'value="Keep me"' in response.text


async def test_edit_page_shows_photos_with_remove_checkboxes(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    await create_via_post(admin_client, category, [photo(1), photo(2)])
    product = await only_product(db_session)

    response = await admin_client.get(f"/admin/products/{product.id}/edit")

    assert response.status_code == 200
    assert response.text.count('name="remove_image_ids"') == 2
    assert 'value="Louis Vuitton"' in response.text
    assert "Главное" in response.text


async def test_edit_product_replaces_and_adds_images(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    cloudinary_storage: set[str],
) -> None:
    category = await add_category(db_session)
    other = await add_category(db_session, "Обувь")
    await create_via_post(admin_client, category, [photo(1, "red"), photo(2, "blue")])
    product = await only_product(db_session)
    first, second = product.images
    old_urls = set(cloudinary_storage)

    response = await admin_client.post(
        f"/admin/products/{product.id}/edit",
        data=product_data(
            other, name="New Name", price="300", remove_image_ids=[str(first.id)]
        ),
        files=[photo(3, "green")],
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/products"
    updated = await only_product(db_session)
    assert updated.name == "New Name"
    assert updated.search_name == "newname"
    assert updated.price == 300
    assert updated.category.name == "Обувь"
    assert len(updated.images) == 2
    assert updated.images[0].id == second.id
    assert [image.position for image in updated.images] == [0, 1]
    new_url = updated.images[1].file_path
    assert new_url not in old_urls
    assert cloudinary_storage == {second.file_path, new_url}
    assert first.file_path not in cloudinary_storage
    assert await count_rows(db_session, ProductImage) == 2


async def test_edit_cannot_exceed_five_images(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    cloudinary_storage: set[str],
) -> None:
    category = await add_category(db_session)
    await create_via_post(admin_client, category, [photo(1), photo(2)])
    product = await only_product(db_session)
    before = set(cloudinary_storage)

    response = await admin_client.post(
        f"/admin/products/{product.id}/edit",
        data=product_data(category, name="Changed"),
        files=[photo(index) for index in range(4)],
    )

    assert response.status_code == 400
    assert TOO_MANY_MESSAGE in response.text
    assert (await only_product(db_session)).name == "Louis Vuitton"
    assert cloudinary_storage == before


async def test_edit_allows_five_after_removing(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    await create_via_post(admin_client, category, [photo(1), photo(2)])
    product = await only_product(db_session)

    response = await admin_client.post(
        f"/admin/products/{product.id}/edit",
        data=product_data(category, remove_image_ids=[str(product.images[0].id)]),
        files=[photo(index) for index in range(4)],
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert [i.position for i in (await only_product(db_session)).images] == [
        0,
        1,
        2,
        3,
        4,
    ]


async def test_edit_unknown_product_returns_404(admin_client: AsyncClient) -> None:
    assert (await admin_client.get("/admin/products/999/edit")).status_code == 404
    response = await admin_client.post(
        "/admin/products/999/edit", data={"name": "x", "price": "1", "category_id": "1"}
    )
    assert response.status_code == 404
    assert (await admin_client.post("/admin/products/999/delete")).status_code == 404


async def test_delete_product_removes_record_and_files(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    cloudinary_storage: set[str],
) -> None:
    category = await add_category(db_session)
    await create_via_post(admin_client, category, [photo(1), photo(2)])
    product = await only_product(db_session)
    assert len(cloudinary_storage) == 2

    response = await admin_client.post(
        f"/admin/products/{product.id}/delete", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/products"
    assert await count_rows(db_session, Product) == 0
    assert await count_rows(db_session, ProductImage) == 0
    assert cloudinary_storage == set()


async def test_delete_ignores_cloudinary_errors(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    category = await add_category(db_session)
    await create_via_post(admin_client, category, [photo(1)])
    product = await only_product(db_session)
    url = product.images[0].file_path

    destroy_mock = MagicMock(side_effect=RuntimeError("Cloudinary is down"))
    monkeypatch.setattr(image_service.cloudinary.uploader, "destroy", destroy_mock)
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "demo")
    monkeypatch.setattr(settings, "CLOUDINARY_API_KEY", "key")
    monkeypatch.setattr(settings, "CLOUDINARY_API_SECRET", "secret")
    monkeypatch.setattr(
        image_service,
        "delete_image",
        lambda u: image_service.asyncio.to_thread(image_service._delete_image_sync, u),
    )

    response = await admin_client.post(
        f"/admin/products/{product.id}/delete", follow_redirects=False
    )

    assert response.status_code == 303
    assert await count_rows(db_session, Product) == 0
    expected_public_id = image_service.extract_public_id(url)
    assert expected_public_id is not None and expected_public_id.startswith(
        "bazarbuy/products/"
    )
    destroy_mock.assert_called_once_with(expected_public_id, resource_type="image")


async def test_local_image_backend_saves_deletes_and_prevents_path_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    upload_dir = tmp_path / "uploads"
    outside_file = tmp_path / "outside.jpg"
    outside_file.write_bytes(b"keep-me")

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", None)
    monkeypatch.setattr(settings, "CLOUDINARY_API_KEY", None)
    monkeypatch.setattr(settings, "CLOUDINARY_API_SECRET", None)

    url = image_service._upload_image_sync(make_image("PNG", "green"))
    assert url.startswith("/uploads/") and url.endswith(".png")
    saved_file = upload_dir / Path(url).name
    assert saved_file.is_file()

    # Path traversal attempt must only touch a file inside upload_dir, never outside.
    image_service._delete_image_sync("/uploads/../outside.jpg")
    assert outside_file.is_file()

    image_service._delete_image_sync(url)
    assert not saved_file.exists()
    # Deleting an already removed file must not raise.
    image_service._delete_image_sync(url)


async def create_three(
    client: AsyncClient, session: AsyncSession, category: Category
) -> list[Product]:
    """Create p1, p2, p3 (in this order), each with one photo; returns [p1, p2, p3]."""
    for index, name in enumerate(["p1", "p2", "p3"]):
        await create_via_post(client, category, [photo(index)], name=name)
    products = await product_service.list_products(session)
    return sorted(products, key=lambda product: product.name)


async def post_reorder(client: AsyncClient, ordered_ids: object) -> Response:
    return await client.post(
        "/admin/products/reorder", json={"ordered_ids": ordered_ids}
    )


async def test_bulk_delete_removes_selected_products_and_files(
    admin_client: AsyncClient,
    db_session: AsyncSession,
    cloudinary_storage: set[str],
) -> None:
    category = await add_category(db_session)
    p1, p2, p3 = await create_three(admin_client, db_session, category)
    keep_urls = {image.file_path for image in p1.images}
    assert len(cloudinary_storage) == 3

    response = await admin_client.post(
        "/admin/products/bulk-delete",
        data={"product_ids": [str(p2.id), str(p3.id)]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/products"
    remaining = await product_service.list_products(db_session)
    assert [product.id for product in remaining] == [p1.id]
    assert await count_rows(db_session, ProductImage) == 1
    assert cloudinary_storage == keep_urls


async def test_bulk_delete_with_empty_list_does_nothing(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    await create_three(admin_client, db_session, category)

    response = await admin_client.post(
        "/admin/products/bulk-delete", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/products"
    assert await count_rows(db_session, Product) == 3


async def test_bulk_delete_ignores_unknown_ids(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    p1, _, _ = await create_three(admin_client, db_session, category)

    response = await admin_client.post(
        "/admin/products/bulk-delete",
        data={"product_ids": [str(p1.id), "99999"]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert await count_rows(db_session, Product) == 2


async def test_reorder_products(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    p1, p2, p3 = await create_three(admin_client, db_session, category)

    response = await post_reorder(admin_client, [p3.id, p1.id, p2.id])

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    products = await product_service.list_products(db_session)
    assert [product.name for product in products] == ["p3", "p1", "p2"]
    assert [product.position for product in products] == [0, 1, 2]
    page = (await admin_client.get("/admin/products")).text
    assert page.index("p3") < page.index("p1") < page.index("p2")


async def test_reorder_with_partial_list_keeps_the_rest_after(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    p1, p2, p3 = await create_three(admin_client, db_session, category)
    # Current list order is p3, p2, p1.

    response = await post_reorder(admin_client, [p1.id])

    assert response.status_code == 200
    products = await product_service.list_products(db_session)
    assert [product.name for product in products] == ["p1", "p3", "p2"]
    assert [product.position for product in products] == [0, 1, 2]


async def test_new_product_goes_first_after_reorder(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    p1, p2, p3 = await create_three(admin_client, db_session, category)
    await post_reorder(admin_client, [p2.id, p3.id, p1.id])

    await create_via_post(admin_client, category, name="p4")

    products = await product_service.list_products(db_session)
    assert [product.name for product in products] == ["p4", "p2", "p3", "p1"]


async def test_reorder_rejects_invalid_data(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    p1, p2, p3 = await create_three(admin_client, db_session, category)
    before = [product.id for product in await product_service.list_products(db_session)]

    for bad in ([], [p1.id, p1.id], [p1.id, 99999], "abc", [None], ["x"]):
        response = await post_reorder(admin_client, bad)
        assert response.status_code == 400, bad
        assert response.json()["status"] == "error"

    response = await admin_client.post(
        "/admin/products/reorder",
        content="not json",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400
    response = await admin_client.post("/admin/products/reorder", json=[1, 2])
    assert response.status_code == 400

    after = [product.id for product in await product_service.list_products(db_session)]
    assert after == before


async def test_products_page_has_bulk_controls_and_handles(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    category = await add_category(db_session)
    await create_three(admin_client, db_session, category)

    page = (await admin_client.get("/admin/products")).text

    assert page.count('class="grip"') == 3
    assert page.count('name="product_ids"') == 3
    assert 'id="select-all"' in page
    assert "Удалить выбранные" in page
    assert "/static/js/admin_products.js" in page
    assert (await admin_client.get("/static/js/admin_products.js")).status_code == 200
