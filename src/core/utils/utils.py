"""General utility functions."""

import logging
from typing import Any, Dict, Optional

import aiohttp
from fastapi import HTTPException

logger = logging.getLogger(__name__)


async def fetch_url(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generic function to fetch data from a URL.

    Args:
        url: The URL to fetch
        method: HTTP method (GET, POST, etc.)
        headers: Optional headers to include in the request
        json_data: Optional JSON data to include in the request body

    Returns:
        The JSON response data

    Raises:
        HTTPException: If the request fails
    """
    try:
        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(url, headers=headers) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        logger.error(f"API error: {error_text}")
                        raise HTTPException(
                            status_code=response.status,
                            detail=(f"Request failed: {response.status}"),
                        )
                    return await response.json()
            elif method.upper() == "POST":
                async with session.post(
                    url, headers=headers, json=json_data
                ) as response:
                    if response.status >= 400:
                        error_text = await response.text()
                        logger.error(f"API error: {error_text}")
                        raise HTTPException(
                            status_code=response.status,
                            detail=f"Request failed: {response.status}",
                        )
                    return await response.json()
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
    except aiohttp.ClientError as e:
        logger.error(f"Request error: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to complete the request"
        )


async def download_binary(
    url: str, headers: Optional[Dict[str, str]] = None
) -> bytes:
    """Download binary data from a URL.

    Args:
        url: The URL to download from
        headers: Optional headers to include in the request

    Returns:
        The downloaded binary data

    Raises:
        HTTPException: If the download fails
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Download error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Failed to download data: {response.status}",
                    )
                return await response.read()
    except aiohttp.ClientError as e:
        logger.error(f"Download error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to download data")
