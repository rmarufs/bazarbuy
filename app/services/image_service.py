import asyncio
import io
import logging
from pathlib import PurePosixPath
from urllib.parse import urlparse

import cloudinary
import cloudinary.uploader
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_IMAGES_PER_PRODUCT = 5
MAX_IMAGE_BYTES = 5 * 1024 * 1024
CLOUDINARY_FOLDER = "bazarbuy/products"

# Allowed Pillow formats mapped to the file extension we validate.
_EXTENSIONS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}

TOO_MANY_MESSAGE = f"У товара может быть не более {MAX_IMAGES_PER_PRODUCT} фотографий"
TOO_BIG_MESSAGE = "Размер фотографии не должен превышать 5 МБ"
INVALID_MESSAGE = "Допустимы только изображения JPEG, PNG или WEBP"
MISSING_CONFIG_MESSAGE = (
    "Загрузка изображений не настроена (отсутствуют ключи Cloudinary)"
)
UPLOAD_ERROR_MESSAGE = "Не удалось загрузить фотографию"


class ImageError(ValueError):
    """Raised for an invalid upload; the message is shown to the admin."""


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
        await file.read(MAX_IMAGE_BYTES + 1) for file in files or [] if file.filename
    ]


def _configure_cloudinary() -> None:
    if (
        not settings.CLOUDINARY_CLOUD_NAME
        or not settings.CLOUDINARY_API_KEY
        or not settings.CLOUDINARY_API_SECRET
    ):
        raise ImageError(MISSING_CONFIG_MESSAGE)
    cloudinary.config(
        cloud_name=settings.CLOUDINARY_CLOUD_NAME,
        api_key=settings.CLOUDINARY_API_KEY,
        api_secret=settings.CLOUDINARY_API_SECRET,
        secure=True,
    )


def extract_public_id(url: str) -> str | None:
    """Extract 'bazarbuy/products/<name>' from a Cloudinary URL."""
    path = urlparse(url).path
    marker = f"/{CLOUDINARY_FOLDER}/"
    idx = path.find(marker)
    if idx == -1:
        return None
    name = PurePosixPath(path[idx + len(marker) :]).stem
    return f"{CLOUDINARY_FOLDER}/{name}" if name else None


def _upload_image_sync(data: bytes) -> str:
    detect_extension(data)
    _configure_cloudinary()
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(data),
            folder=CLOUDINARY_FOLDER,
            resource_type="image",
        )
    except Exception as error:
        logger.exception("Failed to upload image to Cloudinary")
        raise ImageError(UPLOAD_ERROR_MESSAGE) from error
    secure_url = result.get("secure_url")
    if not isinstance(secure_url, str) or not secure_url:
        raise ImageError(UPLOAD_ERROR_MESSAGE)
    return secure_url


async def upload_image(file: UploadFile | bytes) -> str:
    """Validate and upload a single image to Cloudinary; return its secure HTTPS URL."""
    data = (
        file if isinstance(file, bytes) else await file.read(MAX_IMAGE_BYTES + 1)
    )
    return await asyncio.to_thread(_upload_image_sync, data)


def _delete_image_sync(url: str) -> None:
    public_id = extract_public_id(url)
    if not public_id:
        return
    try:
        _configure_cloudinary()
        cloudinary.uploader.destroy(public_id, resource_type="image")
    except Exception:
        logger.warning(
            "Failed to delete image from Cloudinary: %s", url, exc_info=True
        )


async def delete_image(url: str) -> None:
    """Remove an image from Cloudinary by its URL; errors are logged and ignored."""
    await asyncio.to_thread(_delete_image_sync, url)


async def save_images(images: list[bytes]) -> list[str]:
    """Validate all images, then upload them; roll back already uploaded on failure."""
    for data in images:
        detect_extension(data)
    uploaded_urls: list[str] = []
    try:
        for data in images:
            uploaded_urls.append(await upload_image(data))
    except Exception:
        await delete_files(uploaded_urls)
        raise
    return uploaded_urls


async def delete_files(urls: list[str]) -> None:
    """Remove multiple images from Cloudinary; errors are logged and ignored."""
    for url in urls:
        await delete_image(url)
