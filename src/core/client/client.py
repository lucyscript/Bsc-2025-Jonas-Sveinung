"""Fact-checking utility for verifying claims using Factiverse API."""

import logging
import os

import aiohttp
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

API_BASE_URL = "https://dev.factiverse.ai/v1"
FACTIVERSE_API_TOKEN = os.getenv("FACTIVERSE_API_TOKEN")
REQUEST_TIMEOUT = 1000

logger = logging.getLogger(__name__)


async def generate(prompt: str, text: str = "") -> str:
    """Generate context for a given claim using Factiverse API."""
    payload = {
        "logging": False,
        "text": text,
        "prompt": prompt,
    }

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{API_BASE_URL}/generate",
                json=payload,
                headers=headers,
            ) as response:
                if response.status != 200:
                    logger.error(f"Generate API error: {await response.text()}")
                    return ""
                data = await response.json()
                return data.get("full_output", "").replace("**", "*")

    except Exception as e:
        logger.error(f"Generate error: {str(e)}")

    return ""


async def stance_detection(claim: str):
    """Check factual accuracy of a text using Factiverse API.

    Args:
        claim: Claim to check for stance detection

    Returns:
        FactCheckResult containing verdict and supporting evidence

    Raises:
        HTTPException: When API call fails or service is unavailable
    """
    payload = {
        "claim": claim,
    }

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{API_BASE_URL}/stance_detection",
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Stance detection API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Stance detection service error: {error_text}",
                    )
                return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"Unexpected error in stance detection: {str(e)}")
        raise


async def fact_check(url: str):
    """Check factual accuracy of a text using Factiverse API.

    Args:
        url: Source URL of the content

    Returns:
        FactCheckResult containing verdict and supporting evidence

    Raises:
        HTTPException: When API call fails or service is unavailable
    """
    payload = {
        "logging": False,
        "lang": "en",
        "url": url,
    }

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{API_BASE_URL}/fact_check",
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Fact check API error: {error_text}")
                    raise HTTPException(
                        status_code=response.status,
                        detail=f"Fact check service error: {error_text}",
                    )
                return await response.json()

    except aiohttp.ClientError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fact check service error: {str(e)}",
        )


async def detect_claims(text: str, threshold: float = 0.7) -> list[str]:
    """Detect individual claims in text using Factiverse API.

    Args:
        text: Text to check for claims
        threshold: Minimum confidence threshold for claims

    Returns:
        Claims detected in the text

    Raises:
        HTTPException: When API call fails or service is unavailable
    """
    payload = {
        "logging": False,
        "text": text,
        "claimScoreThreshold": threshold,
    }

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{API_BASE_URL}/claim_detection",
                json=payload,
                headers=headers,
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"Claim detection API error: {error_text}")
                    return []

                claims_data = await response.json()
                claims = []

                if "detectedClaims" in claims_data:
                    for claim in claims_data["detectedClaims"]:
                        claim_text = str(claim.get("claim", "")).strip()
                        if claim_text:
                            claims.append(claim_text)

                return claims

    except aiohttp.ClientError as e:
        print(f"Claim detection API error: {str(e)}")
        return []
    except KeyError as e:
        print(f"Missing expected field in response: {str(e)}")
        return []
    except Exception as e:
        print(f"Error processing claims: {str(e)}")
        return []
