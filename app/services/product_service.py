from collections.abc import Collection

from pydantic import ValidationError
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Product, ProductImage
from app.schemas.product import ProductInput, normalize_search_name
from app.services import category_service, image_service

_FIELD_MESSAGES = {
    "name": "Название должно содержать от 1 до 200 символов",
    "price": "Цена должна быть целым числом больше 0",
    "category_id": "Выберите категорию",
}
_DEFAULT_MESSAGE = "Проверьте данные формы"
_INVALID_ORDER_MESSAGE = "Некорректный порядок товаров"

# Related data is always loaded explicitly (no lazy loading).
_WITH_RELATIONS = (selectinload(Product.category), selectinload(Product.images))


class ProductError(ValueError):
    """Raised for invalid product data; the message is shown to the admin."""


class ProductNotFoundError(ProductError):
    def __init__(self) -> None:
        super().__init__("Товар не найден")


def _parse_input(
    name: str, description: str, price: str | int, category_id: str | int
) -> ProductInput:
    try:
        return ProductInput(
            name=name, description=description, price=price, category_id=category_id
        )
    except ValidationError as error:
        field = str(error.errors()[0]["loc"][0])
        raise ProductError(_FIELD_MESSAGES.get(field, _DEFAULT_MESSAGE)) from error


async def _ensure_category_exists(session: AsyncSession, category_id: int) -> None:
    if await category_service.get_category(session, category_id) is None:
        raise ProductError("Выбранная категория не найдена")


async def _store_images(images: list[bytes], existing_count: int = 0) -> list[str]:
    """Validate and save new images, turning image errors into product errors."""
    try:
        image_service.check_image_count(existing_count + len(images))
        return await image_service.save_images(images)
    except image_service.ImageError as error:
        raise ProductError(str(error)) from error


async def _top_position(session: AsyncSession) -> int:
    """Position that puts a new product before all existing ones."""
    lowest = await session.scalar(select(func.min(Product.position)))
    return 0 if lowest is None else lowest - 1


def _ordered_products() -> Select[tuple[Product]]:
    """Products with related data, ordered by position, then newest first."""
    return (
        select(Product)
        .options(*_WITH_RELATIONS)
        .order_by(Product.position, Product.created_at.desc(), Product.id.desc())
        .execution_options(populate_existing=True)
    )


async def list_products(session: AsyncSession) -> list[Product]:
    """All products, ordered by position, then newest first."""
    result = await session.execute(_ordered_products())
    return list(result.scalars().all())


async def list_catalog_products(
    session: AsyncSession,
    category_id: int | None = None,
    query: str | None = None,
) -> list[Product]:
    """Products for the public catalog, optionally filtered by category and search.

    The search ignores letter case and whitespace (see `normalize_search_name`).
    """
    statement = _ordered_products()
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    needle = normalize_search_name(query or "")
    if needle:
        statement = statement.where(
            Product.search_name.contains(needle, autoescape=True)
        )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_product(session: AsyncSession, product_id: int) -> Product | None:
    # populate_existing: always reflect the database, even for objects already in the session.
    result = await session.execute(
        select(Product)
        .where(Product.id == product_id)
        .options(*_WITH_RELATIONS)
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def create_product(
    session: AsyncSession,
    name: str,
    description: str,
    price: str | int,
    category_id: str | int,
    images: list[bytes],
) -> Product:
    data = _parse_input(name, description, price, category_id)
    await _ensure_category_exists(session, data.category_id)
    saved_paths = await _store_images(images)
    try:
        product = Product(
            name=data.name,
            description=data.description,
            price=data.price,
            category_id=data.category_id,
            search_name=normalize_search_name(data.name),
            position=await _top_position(session),
        )
        session.add(product)
        await session.flush()
        session.add_all(
            ProductImage(product_id=product.id, file_path=path, position=index)
            for index, path in enumerate(saved_paths)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await image_service.delete_files(saved_paths)
        raise
    return product


async def update_product(
    session: AsyncSession,
    product_id: int,
    name: str,
    description: str,
    price: str | int,
    category_id: str | int,
    remove_image_ids: Collection[int],
    new_images: list[bytes],
) -> Product:
    """Update fields, drop the chosen photos and add new ones (5 photos max)."""
    product = await get_product(session, product_id)
    if product is None:
        raise ProductNotFoundError
    data = _parse_input(name, description, price, category_id)
    await _ensure_category_exists(session, data.category_id)

    removed = [image for image in product.images if image.id in remove_image_ids]
    kept = [image for image in product.images if image.id not in remove_image_ids]
    removed_paths = [image.file_path for image in removed]
    saved_paths = await _store_images(new_images, existing_count=len(kept))
    try:
        product.name = data.name
        product.search_name = normalize_search_name(data.name)
        product.description = data.description
        product.price = data.price
        product.category_id = data.category_id
        for image in removed:
            await session.delete(image)
        for position, image in enumerate(kept):
            image.position = position
        session.add_all(
            ProductImage(
                product_id=product.id, file_path=path, position=len(kept) + index
            )
            for index, path in enumerate(saved_paths)
        )
        await session.commit()
    except Exception:
        await session.rollback()
        await image_service.delete_files(saved_paths)
        raise
    await image_service.delete_files(removed_paths)
    return product


async def delete_product(session: AsyncSession, product_id: int) -> None:
    """Delete the product and all its image files."""
    product = await get_product(session, product_id)
    if product is None:
        raise ProductNotFoundError
    file_paths = [image.file_path for image in product.images]
    await session.delete(product)
    await session.commit()
    await image_service.delete_files(file_paths)


async def bulk_delete_products(session: AsyncSession, product_ids: list[int]) -> int:
    """Delete the chosen products and their image files; unknown ids are ignored.

    Returns the number of deleted products.
    """
    unique_ids = set(product_ids)
    if not unique_ids:
        return 0
    result = await session.execute(
        select(Product)
        .where(Product.id.in_(unique_ids))
        .options(selectinload(Product.images))
        .execution_options(populate_existing=True)
    )
    products = list(result.scalars().all())
    file_paths = [image.file_path for p in products for image in p.images]
    for product in products:
        await session.delete(product)
    await session.commit()
    await image_service.delete_files(file_paths)
    return len(products)


async def reorder_products(session: AsyncSession, ordered_ids: list[int]) -> None:
    """Make the listed products appear in this order, with positions 0, 1, 2, ...

    Products missing from the list (e.g. added in another tab) keep their
    relative order and go after the listed ones.
    """
    if not ordered_ids or len(set(ordered_ids)) != len(ordered_ids):
        raise ProductError(_INVALID_ORDER_MESSAGE)
    result = await session.execute(
        select(Product)
        .order_by(Product.position, Product.created_at.desc(), Product.id.desc())
        .execution_options(populate_existing=True)
    )
    products = list(result.scalars().all())
    by_id = {product.id: product for product in products}
    if any(product_id not in by_id for product_id in ordered_ids):
        raise ProductError(_INVALID_ORDER_MESSAGE)
    listed = set(ordered_ids)
    unlisted = [product for product in products if product.id not in listed]
    ordered = [by_id[product_id] for product_id in ordered_ids] + unlisted
    for position, product in enumerate(ordered):
        product.position = position
    await session.commit()
