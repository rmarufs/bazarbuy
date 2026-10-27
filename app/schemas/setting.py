import re

from pydantic import BaseModel, field_validator

_SEPARATORS = re.compile(r"[\s\-()]")
_PHONE_PATTERN = re.compile(r"\+?\d{7,15}")


class SettingUpdate(BaseModel):
    """WhatsApp number: digits with an optional leading '+', or empty."""

    whatsapp_number: str

    @field_validator("whatsapp_number")
    @classmethod
    def normalize_number(cls, value: str) -> str:
        cleaned = _SEPARATORS.sub("", value)
        if cleaned and not _PHONE_PATTERN.fullmatch(cleaned):
            raise ValueError("invalid WhatsApp number")
        return cleaned
