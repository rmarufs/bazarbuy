import asyncio
import io
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import settings

MAX_IMAGES_PER_PRODUCT = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Allowed Pillow formats mapped to the file extension we store.
_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

TOO_MANY_MESSAGE = f"У товара может быть не более {MAX_IMAGES_PER_PRODUCT} фотографий"
TOO_BIG_MESSAGE = "Размер фотографии не должен превышать 5 МБ"
INVALID_MESSAGE = "Допустимы только изображения JPEG, PNG или WEBP"


class ImageError(ValueError):
    """Raised for an invalid upload; the message is shown to the admin."""


def _upload_dir() -> Path:
    return Path(settings.UPLOAD_DIR)


def check_image_count(total: int) -> None:
    if total > MAX_IMAGES_PER_PRODUCT:
        raise ImageError(TOO_MANY_MESSAGE)


def detect_extension(data: bytes) -> str:
    """Check size and content with Pillow; return the extension for the real format."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError(TOO_BIG_MESSAGE)
    try:
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
            image.verify()
    except (
        UnidentifiedImageError,
        OSError,
        SyntaxError,
        ValueError,
        Image.DecompressionBombError,
    ) as error:
        raise ImageError(INVALID_MESSAGE) from error
    extension = _EXTENSIONS.get(image_format or "")
    if extension is None:
        raise ImageError(INVALID_MESSAGE)
    return extension


async def read_uploads(files: list[UploadFile] | None) -> list[bytes]:
    """Read the chosen files; the empty file part browsers send is skipped."""
    return [
        await file.read(MAX_IMAGE_BYTES + 1)
        for file in files or []
        if file.filename
    ]


def _save_images_sync(images: list[bytes]) -> list[str]:
    extensions = [detect_extension(data) for data in images]
    directory = _upload_dir()
    directory.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    try:
        for data, extension in zip(images, extensions, strict=True):
            file_name = f"{uuid4().hex}.{extension}"
            (directory / file_name).write_bytes(data)
            saved.append(file_name)
    except OSError:
        _delete_files_sync(saved)
        raise
    return saved


async def save_images(images: list[bytes]) -> list[str]:
    """Validate and store images; all are saved or none. Returns relative paths."""
    return await asyncio.to_thread(_save_images_sync, images)


def _delete_files_sync(file_paths: list[str]) -> None:
    directory = _upload_dir()
    for file_path in file_paths:
        # Only the file name is used, so a stored path can never leave the upload dir.
        (directory / Path(file_path).name).unlink(missing_ok=True)


async def delete_files(file_paths: list[str]) -> None:
    """Remove files from disk; files that are already gone are ignored."""
    await asyncio.to_thread(_delete_files_sync, file_paths)
