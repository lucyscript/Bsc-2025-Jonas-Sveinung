"""Image utility for extracting image data."""

import logging
import os
from io import BytesIO

import pytesseract
from fastapi import HTTPException
from PIL import Image

from src.core.utils.utils import download_binary
from src.platform.telegram.utils import get_telegram_image_url
from src.platform.whatsapp.utils import get_whatsapp_image_url

logger = logging.getLogger(__name__)


async def get_image_url(image_id: str, platform: str = "") -> str:
    """Retrieve the image URL by calling the appropriate function.

    Args:
        image_id: The ID of the image to retrieve
        platform: The platform to retrieve from ('whatsapp' or 'telegram')

    Returns:
        The URL of the image
    """
    if platform == "whatsapp":
        return await get_whatsapp_image_url(image_id)
    elif platform == "telegram":
        return await get_telegram_image_url(image_id)
    else:
        raise HTTPException(
            status_code=400, detail=f"Unsupported platform: {platform}"
        )


async def download_image(image_url: str) -> bytes:
    """Download the image from the provided URL."""
    try:
        if "api.telegram.org" in image_url:
            return await download_binary(image_url)

        headers = {
            "Authorization": f"Bearer {os.getenv('WHATSAPP_TOKEN')}",
        }
        return await download_binary(image_url, headers)
    except Exception as e:
        logger.error(f"Failed to download image: {e}")
        raise


def extract_text_from_image(image_bytes: bytes) -> str:
    """Extract text from image using OCR."""
    try:
        image = Image.open(BytesIO(image_bytes))
        text = pytesseract.image_to_string(image)
        return text
    except Exception as e:
        logger.error(f"OCR error: {e}")
        return ""
