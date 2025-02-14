"""Fact-checking utility for verifying claims using Factiverse API."""

import json
import os

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configuration
FACTIVERSE_API_TOKEN = os.getenv("FACTIVERSE_API_TOKEN")
if not FACTIVERSE_API_TOKEN:
    raise ValueError("FACTIVERSE_API_TOKEN not found in .env file")

API_BASE_URL = os.getenv("FACTIVERSE_API_URL", "https://dev.factiverse.ai/v1")
GENERATE_PROMPT = os.getenv("GENERATE_PROMPT")
REQUEST_TIMEOUT = 30  # seconds


class FactCheckResult(BaseModel):
    """Structured result from fact-checking."""

    claim: str
    verdict: str
    confidence: float
    sources: list[str]
    evidence: list[dict]
    explanation: str

    @property
    def is_supported(self) -> bool:
        """Check if the claim is supported by evidence."""
        return self.verdict.lower() == "supported"

    @property
    def confidence_percentage(self) -> float:
        """Get confidence as a percentage."""
        return self.confidence * 100


async def generate(
    text: str,
):
    """Generate additional context for a given claim using Factiverse API."""
    payload = {
        "logging": False,
        "lang": "",
        "text": text,
        "prompt": GENERATE_PROMPT,
    }

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/generate",
                content=json.dumps(payload),
                headers=headers,
            )
            response.raise_for_status()
            json_response = response.json()
            return json_response["full_output"]

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Fact check service error: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f"Service temporarily unavailable: {str(e)}"
        )


async def fact_check(
    claim: str,
    text: str,
    collection: str = "test",
) -> FactCheckResult:
    """Check factual accuracy of a text using Factiverse API.

    Args:
        claim: Claim to fact check
        text: Text content to fact check
        lang: Language of the content
        domains: Specific domains to search (defaults to all domains)
        url: Optional source URL of the content
        collection: Factiverse collection to use

    Returns:
        FactCheckResult containing verdict and supporting evidence

    Raises:
        HTTPException: When API call fails or service is unavailable
    """
    payload = {
        "logging": False,
        "lang": "",
        "collection": collection,
        "text": text,
        "claims": [claim],
        "url": "",
        "domainsToSearch": [],
    }

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/fact_check",
                content=json.dumps(payload),
                headers=headers,
            )
            response.raise_for_status()
            return parse_factiverse_response(response.json())

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Fact check service error: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f"Service temporarily unavailable: {str(e)}"
        )


def parse_factiverse_response(response: dict) -> FactCheckResult:
    """Parse raw Factiverse API response into structured format.

    Args:
        response: Raw JSON response from Factiverse API

    Returns:
        Structured FactCheckResult
    """
    # Get first claim with fallbacks for missing data
    first_claim = response.get("claims", [{}])[0]

    # Map the final prediction to a verdict
    prediction = first_claim.get("finalPrediction")
    verdict = "Supported" if prediction == 1 else "Refuted"

    return FactCheckResult(
        claim=first_claim.get("claim", "No claim text available"),
        verdict=verdict,
        confidence=first_claim.get(
            "finalScore", 0.0
        ),  # This is the actual confidence score
        sources=first_claim.get("sources", []),
        evidence=first_claim.get("evidence", []),
        explanation=first_claim.get("explanation", "No explanation available"),
    )


def format_human_readable_result(result: FactCheckResult) -> str:
    """Format fact-check results into a human-readable message.

    Args:
        result: Structured fact-check result

    Returns:
        Formatted message with emojis and markdown
    """
    verdict_emoji = "✅" if result.is_supported else "❌"
    confidence_pct = f"{result.confidence_percentage:.1f}%"

    message = [
        "🔍 *Fact Check Results:*\n",
        f"*Claim:* {result.claim}",
        f"*Verdict:* {verdict_emoji} {result.verdict}",
        f"*Confidence:* {confidence_pct}\n",
    ]

    # Add evidence if available
    if result.evidence:
        message.append("*Top Evidence:*")
        for idx, evidence in enumerate(result.evidence[:2], 1):
            source = (
                evidence.get("title")
                or evidence.get("domainName")
                or "Unknown source"
            )
            url = evidence.get("url", "#")
            snippet = evidence.get("evidenceSnippet", "")
            if snippet:
                snippet = (
                    f"{snippet[:200]}..." if len(snippet) > 200 else snippet
                )

            message.extend([f"{idx}. [{source}]({url})", f"{snippet}\n"])

    return "\n".join(message)
