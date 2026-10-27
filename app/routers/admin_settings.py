from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin_id
from app.core.templating import templates
from app.services import setting_service
from app.services.setting_service import InvalidWhatsAppNumberError

router = APIRouter(prefix="/admin", dependencies=[Depends(get_current_admin_id)])


@router.get("/settings")
async def settings_page(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    saved: str | None = None,
) -> Response:
    setting = await setting_service.get_setting(db)
    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {
            "whatsapp_number": setting.whatsapp_number,
            "saved": saved == "1",
            "error": None,
        },
    )


@router.post("/settings")
async def update_settings(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    whatsapp_number: Annotated[str, Form()],
) -> Response:
    try:
        await setting_service.update_whatsapp_number(db, whatsapp_number)
    except InvalidWhatsAppNumberError as error:
        return templates.TemplateResponse(
            request,
            "admin/settings.html",
            {"whatsapp_number": whatsapp_number, "saved": False, "error": str(error)},
            status_code=400,
        )
    return RedirectResponse("/admin/settings?saved=1", status_code=303)
