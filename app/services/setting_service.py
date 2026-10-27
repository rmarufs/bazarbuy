from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting
from app.schemas.setting import SettingUpdate


class InvalidWhatsAppNumberError(ValueError):
    """Raised when the submitted WhatsApp number has an invalid format."""


async def get_setting(session: AsyncSession) -> Setting:
    """Return the single Setting row, creating it with an empty number if missing."""
    result = await session.execute(select(Setting).order_by(Setting.id).limit(1))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = Setting(whatsapp_number="")
        session.add(setting)
        await session.commit()
    return setting


async def update_whatsapp_number(session: AsyncSession, raw_number: str) -> Setting:
    """Validate, normalize and save the WhatsApp number."""
    try:
        data = SettingUpdate(whatsapp_number=raw_number)
    except ValidationError as error:
        raise InvalidWhatsAppNumberError(
            "Введите номер в формате +992XXXXXXXXX"
        ) from error
    setting = await get_setting(session)
    setting.whatsapp_number = data.whatsapp_number
    await session.commit()
    return setting
