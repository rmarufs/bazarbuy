from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.templating import templates
from app.services import category_service, product_service, setting_service

router = APIRouter()


@router.get("/")
async def catalog_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    category_id: int | None = None,
    q: str | None = None,
) -> Response:
    products = await product_service.list_catalog_products(db, category_id, q)
    categories = await category_service.list_categories(db)
    return templates.TemplateResponse(
        request,
        "public/catalog.html",
        {
            "products": products,
            "categories": categories,
            "selected_category_id": category_id,
            "q": (q or "").strip(),
        },
    )


@router.get("/products/{product_id}")
async def product_page(
    request: Request,
    product_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    product = await product_service.get_product(db, product_id)
    if product is None:
        return templates.TemplateResponse(
            request, "public/404.html", status_code=status.HTTP_404_NOT_FOUND
        )
    return templates.TemplateResponse(
        request, "public/product_detail.html", {"product": product}
    )


@router.get("/about")
async def about_page(request: Request) -> Response:
    return templates.TemplateResponse(request, "public/about.html")


@router.get("/contacts")
async def contacts_page(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    setting = await setting_service.get_setting(db)
    return templates.TemplateResponse(
        request,
        "public/contacts.html",
        {
            "whatsapp_number": setting.whatsapp_number,
            "whatsapp_url": setting_service.build_whatsapp_url(
                setting.whatsapp_number
            ),
        },
    )
