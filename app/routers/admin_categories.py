from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin_id
from app.core.templating import templates
from app.services import category_service
from app.services.category_service import CategoryError, CategoryNotFoundError

router = APIRouter(
    prefix="/admin/categories", dependencies=[Depends(get_current_admin_id)]
)

CATEGORIES_URL = "/admin/categories"


async def render_page(
    request: Request,
    db: AsyncSession,
    error: str | None = None,
    new_name: str = "",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    categories = await category_service.list_categories(db)
    return templates.TemplateResponse(
        request,
        "admin/categories.html",
        {"categories": categories, "error": error, "new_name": new_name},
        status_code=status_code,
    )


async def render_error(
    request: Request, db: AsyncSession, error: CategoryError, new_name: str = ""
) -> Response:
    if isinstance(error, CategoryNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error))
    return await render_page(
        request,
        db,
        error=str(error),
        new_name=new_name,
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("")
async def categories_page(
    request: Request, db: Annotated[AsyncSession, Depends(get_db)]
) -> Response:
    return await render_page(request, db)


@router.post("")
async def create_category(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()],
) -> Response:
    try:
        await category_service.create_category(db, name)
    except CategoryError as error:
        return await render_error(request, db, error, new_name=name)
    return RedirectResponse(CATEGORIES_URL, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{category_id}/rename")
async def rename_category(
    request: Request,
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    name: Annotated[str, Form()],
) -> Response:
    try:
        await category_service.update_category(db, category_id, name)
    except CategoryError as error:
        return await render_error(request, db, error)
    return RedirectResponse(CATEGORIES_URL, status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{category_id}/delete")
async def delete_category(
    request: Request,
    category_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    try:
        await category_service.delete_category(db, category_id)
    except CategoryError as error:
        return await render_error(request, db, error)
    return RedirectResponse(CATEGORIES_URL, status_code=status.HTTP_303_SEE_OTHER)
