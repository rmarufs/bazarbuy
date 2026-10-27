from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category, Product
from app.schemas.category import CategoryName, CategoryWithCount


class CategoryError(ValueError):
    """Base error for category operations; the message is shown to the admin."""


class InvalidCategoryNameError(CategoryError):
    def __init__(self) -> None:
        super().__init__("Название должно содержать от 1 до 100 символов")


class DuplicateCategoryError(CategoryError):
    def __init__(self) -> None:
        super().__init__("Категория с таким названием уже существует")


class CategoryNotEmptyError(CategoryError):
    def __init__(self) -> None:
        super().__init__("Нельзя удалить категорию, пока в ней есть товары")


class CategoryNotFoundError(CategoryError):
    def __init__(self) -> None:
        super().__init__("Категория не найдена")


def _validate_name(raw_name: str) -> str:
    try:
        return CategoryName(name=raw_name).name
    except ValidationError as error:
        raise InvalidCategoryNameError from error


async def _ensure_name_is_free(
    session: AsyncSession, name: str, exclude_id: int | None = None
) -> None:
    """Raise if another category has the same name, ignoring letter case."""
    result = await session.execute(select(Category.id, Category.name))
    wanted = name.casefold()
    for category_id, existing in result.all():
        if category_id != exclude_id and existing.casefold() == wanted:
            raise DuplicateCategoryError


async def list_categories(session: AsyncSession) -> list[CategoryWithCount]:
    """Return all categories with their product counts, sorted by name."""
    products_count = func.count(Product.id)
    result = await session.execute(
        select(Category.id, Category.name, products_count)
        .outerjoin(Product, Product.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.name)
    )
    return [
        CategoryWithCount(id=row[0], name=row[1], products_count=row[2])
        for row in result.all()
    ]


async def get_category(session: AsyncSession, category_id: int) -> Category | None:
    return await session.get(Category, category_id)


async def _get_category_or_raise(session: AsyncSession, category_id: int) -> Category:
    category = await get_category(session, category_id)
    if category is None:
        raise CategoryNotFoundError
    return category


async def _commit_or_duplicate(session: AsyncSession) -> None:
    """Commit; the unique constraint turns a race on the name into a duplicate error."""
    try:
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise DuplicateCategoryError from error


async def create_category(session: AsyncSession, raw_name: str) -> Category:
    name = _validate_name(raw_name)
    await _ensure_name_is_free(session, name)
    category = Category(name=name)
    session.add(category)
    await _commit_or_duplicate(session)
    return category


async def update_category(
    session: AsyncSession, category_id: int, raw_name: str
) -> Category:
    category = await _get_category_or_raise(session, category_id)
    name = _validate_name(raw_name)
    await _ensure_name_is_free(session, name, exclude_id=category_id)
    category.name = name
    await _commit_or_duplicate(session)
    return category


async def delete_category(session: AsyncSession, category_id: int) -> None:
    """Delete an empty category; categories that have products are protected."""
    category = await _get_category_or_raise(session, category_id)
    products_count = await session.scalar(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    )
    if products_count:
        raise CategoryNotEmptyError
    try:
        await session.delete(category)
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise CategoryNotEmptyError from error
