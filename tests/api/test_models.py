import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Admin, Category, Product, ProductImage, Setting


async def create_product(session: AsyncSession) -> Product:
    category = Category(name="Bags")
    product = Product(
        name="Louis Vuitton",
        price=250,
        search_name="louisvuitton",
        category=category,
        images=[
            ProductImage(file_path="b.jpg", position=1),
            ProductImage(file_path="a.jpg", position=0),
        ],
    )
    session.add(product)
    await session.commit()
    return product


async def test_product_with_category_and_images(db_session: AsyncSession) -> None:
    product = await create_product(db_session)

    result = await db_session.execute(
        select(Product)
        .where(Product.id == product.id)
        .options(selectinload(Product.category), selectinload(Product.images))
        .execution_options(populate_existing=True)
    )
    loaded = result.scalar_one()

    assert loaded.category.name == "Bags"
    assert loaded.description == ""
    assert loaded.position == 0
    assert loaded.created_at is not None
    assert [image.file_path for image in loaded.images] == ["a.jpg", "b.jpg"]


async def test_lazy_loading_is_forbidden(db_session: AsyncSession) -> None:
    product = await create_product(db_session)
    db_session.expire_all()

    loaded = (await db_session.execute(select(Product))).scalar_one()
    with pytest.raises(Exception, match="lazy='raise'"):
        _ = loaded.images
    assert loaded.id == product.id


async def test_deleting_product_cascades_images(db_session: AsyncSession) -> None:
    product = await create_product(db_session)

    await db_session.delete(product)
    await db_session.commit()

    count = await db_session.scalar(select(func.count()).select_from(ProductImage))
    assert count == 0


async def test_category_with_products_cannot_be_deleted(
    db_session: AsyncSession,
) -> None:
    product = await create_product(db_session)
    category = await db_session.get(Category, product.category_id)
    assert category is not None

    await db_session.delete(category)
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_create_admin_and_setting(db_session: AsyncSession) -> None:
    db_session.add_all([Admin(username="owner", password_hash="hash"), Setting()])
    await db_session.commit()

    admin = (await db_session.execute(select(Admin))).scalar_one()
    setting = (await db_session.execute(select(Setting))).scalar_one()
    assert admin.username == "owner"
    assert setting.whatsapp_number == ""
