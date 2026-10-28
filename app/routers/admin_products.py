from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin_id
from app.core.templating import templates
from app.models import Product
from app.schemas.product import ReorderRequest
from app.services import category_service, image_service, product_service
from app.services.product_service import ProductError, ProductNotFoundError

router = APIRouter(
    prefix="/admin/products", dependencies=[Depends(get_current_admin_id)]
)

PRODUCTS_URL = "/admin/products"

FormValues = dict[str, str | int]


def form_values_of(product: Product) -> FormValues:
    return {
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "category_id": product.category_id,
    }


def submitted_values(
    name: str, description: str, price: str, category_id: str
) -> FormValues:
    return {
        "name": name,
        "description": description,
        "price": price,
        "category_id": category_id,
    }


def not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(ProductNotFoundError()))


async def render_form(
    request: Request,
    db: AsyncSession,
    product: Product | None,
    form: FormValues,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> Response:
    categories = await category_service.list_categories(db)
    return templates.TemplateResponse(
        request,
        "admin/product_form.html",
        {
            "product": product,
            "form": form,
            "categories": categories,
            "error": error,
            "max_images": image_service.MAX_IMAGES_PER_PRODUCT,
        },
        status_code=status_code,
    )


@router.get("")
async def products_page(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    products = await product_service.list_products(db)
    return templates.TemplateResponse(
        request, "admin/products.html", {"products": products}
    )


@router.get("/new")
async def new_product_page(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    return await render_form(
        request, db, product=None, form=submitted_values("", "", "", "")
    )


@router.post("/new")
async def create_product(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    price: Annotated[str, Form()] = "",
    category_id: Annotated[str, Form()] = "",
    photos: Annotated[list[UploadFile] | None, File()] = None,
) -> Response:
    try:
        await product_service.create_product(
            db,
            name,
            description,
            price,
            category_id,
            await image_service.read_uploads(photos),
        )
    except ProductError as error:
        return await render_form(
            request,
            db,
            product=None,
            form=submitted_values(name, description, price, category_id),
            error=str(error),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(PRODUCTS_URL, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/bulk-delete")
async def bulk_delete_products(
    db: Annotated[AsyncSession, Depends(get_db)],
    product_ids: Annotated[list[int] | None, Form()] = None,
) -> RedirectResponse:
    await product_service.bulk_delete_products(db, product_ids or [])
    return RedirectResponse(PRODUCTS_URL, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/reorder")
async def reorder_products(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> JSONResponse:
    try:
        payload = ReorderRequest.model_validate(await request.json())
        await product_service.reorder_products(db, payload.ordered_ids)
    except ValueError as error:  # bad JSON, bad shape (ValidationError) or ProductError
        message = (
            str(error)
            if isinstance(error, ProductError)
            else "Некорректный порядок товаров"
        )
        return JSONResponse(
            {"status": "error", "detail": message},
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return JSONResponse({"status": "ok"})


@router.get("/{product_id}/edit")
async def edit_product_page(
    request: Request,
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    product = await product_service.get_product(db, product_id)
    if product is None:
        raise not_found()
    return await render_form(request, db, product, form_values_of(product))


@router.post("/{product_id}/edit")
async def edit_product(
    request: Request,
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()] = "",
    description: Annotated[str, Form()] = "",
    price: Annotated[str, Form()] = "",
    category_id: Annotated[str, Form()] = "",
    remove_image_ids: Annotated[list[int] | None, Form()] = None,
    photos: Annotated[list[UploadFile] | None, File()] = None,
) -> Response:
    try:
        await product_service.update_product(
            db,
            product_id,
            name,
            description,
            price,
            category_id,
            remove_image_ids or [],
            await image_service.read_uploads(photos),
        )
    except ProductNotFoundError as error:
        raise not_found() from error
    except ProductError as error:
        product = await product_service.get_product(db, product_id)
        return await render_form(
            request,
            db,
            product=product,
            form=submitted_values(name, description, price, category_id),
            error=str(error),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return RedirectResponse(PRODUCTS_URL, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{product_id}/delete")
async def delete_product(
    product_id: int, db: Annotated[AsyncSession, Depends(get_db)]
) -> RedirectResponse:
    try:
        await product_service.delete_product(db, product_id)
    except ProductNotFoundError as error:
        raise not_found() from error
    return RedirectResponse(PRODUCTS_URL, status_code=status.HTTP_303_SEE_OTHER)
