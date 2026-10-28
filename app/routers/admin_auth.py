from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    LOGIN_URL,
    SESSION_COOKIE_NAME,
    create_session_token,
    get_session_admin_id,
    session_cookie_params,
)
from app.core.templating import templates
from app.services import auth_service

router = APIRouter(prefix="/admin")

SETTINGS_URL = "/admin/settings"
PRODUCTS_URL = "/admin/products"


@router.get("")
async def admin_index() -> RedirectResponse:
    return RedirectResponse(PRODUCTS_URL, status_code=303)


@router.get("/login")
async def login_page(request: Request) -> Response:
    if get_session_admin_id(request) is not None:
        return RedirectResponse(SETTINGS_URL, status_code=303)
    return templates.TemplateResponse(request, "admin/login.html", {"error": None})


@router.post("/login")
async def login(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    admin = await auth_service.authenticate(db, username, password)
    if admin is None:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"error": "Неверный логин или пароль", "username": username},
            status_code=401,
        )
    response = RedirectResponse(SETTINGS_URL, status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, create_session_token(admin.id), **session_cookie_params()
    )
    return response


@router.post("/logout")
async def logout() -> RedirectResponse:
    response = RedirectResponse(LOGIN_URL, status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response
