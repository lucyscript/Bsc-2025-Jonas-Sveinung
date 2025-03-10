"""Fact-checking utility for verifying claims using Factiverse API."""

import asyncio
import logging
import os

import httpx
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
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/generate",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json().get("full_output", "").replace("**", "*")

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
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/stance_detection",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"Unexpected error in stance detection: {str(e)}")
        raise


async def fact_check(url: str):
    """Check factual accuracy of a text using Factiverse API.

    Args:
        claims: List of claims to fact check
        url: Optional source URL of the content
        message: Original text containing claims (optional)

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
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/fact_check",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Fact check service error: {e.response.text}",
        )


async def detect_claims(text: str, threshold: float = 0.9) -> list[str]:
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
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE_URL}/claim_detection",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            claims_data = response.json()
            claims = []

            if "detectedClaims" in claims_data:
                for claim in claims_data["detectedClaims"]:
                    claim_text = str(claim.get("claim", "")).strip()
                    if claim_text:
                        claims.append(claim_text)

            return claims

    except httpx.HTTPStatusError as e:
        print(f"Claim detection API error: {str(e)}")
        return []
    except KeyError as e:
        print(f"Missing expected field in response: {str(e)}")
        return []
    except Exception as e:
        print(f"Error processing claims: {str(e)}")
        return []


def clean_facts(json_data: dict | None) -> list:
    """Extract relevant fact-check results with dynamic evidence balancing."""
    cleaned_results: list[dict] = []

    if json_data is None:
        return cleaned_results
    try:
        if (
            "collection" in json_data
            and json_data["collection"] == "stance_detection"
        ):
            evidence_list = json_data.get("evidence", [])
            claim_text = json_data.get("claim", "")
            if not evidence_list:
                return [{"error": f"No evidence found for claim: {claim_text}"}]
            summary = " ".join(
                str(item) for item in json_data.get("summary", [])
            ).replace('"', "'")
            fix = json_data.get("fix", "").replace('"', "'")

            final_verdict = "Uncertain"
            if json_data.get("finalPrediction") is not None:
                final_verdict = (
                    "Incorrect"
                    if json_data.get("finalPrediction") == 0
                    else "Correct"
                )

            if final_verdict == "Incorrect":
                confidence = round(
                    (1 - (json_data.get("finalScore") or 0)) * 100, 2
                )
            else:
                confidence = round((json_data.get("finalScore") or 0) * 100, 2)

            supporting_evidence = []
            refuting_evidence = []

            for evidence in evidence_list:
                label = evidence.get("labelDescription", "")
                if label not in ["SUPPORTS", "REFUTES"]:
                    continue

                evidence_entry = {
                    "labelDescription": label,
                    "domain_name": evidence.get("domainName", ""),
                    "domainReliability": evidence.get(
                        "domain_reliability", {}
                    ).get("Reliability", "Unknown"),
                    "url": evidence.get("url", ""),
                }

                if label == "SUPPORTS":
                    supporting_evidence.append(evidence_entry)
                else:
                    refuting_evidence.append(evidence_entry)

            cleaned_results.append(
                {
                    "claim": claim_text,
                    "verdict": final_verdict,
                    "confidence_percentage": confidence,
                    "summary": summary,
                    "fix": fix,
                    "supporting_evidence": supporting_evidence,
                    "refuting_evidence": refuting_evidence,
                }
            )
        else:
            for text_item in json_data.get("text", []):
                evidence_list = text_item.get("evidence", [])
                if not evidence_list:
                    cleaned_results.append({"error": "No evidence found"})
                    continue
                claim_text = text_item.get("claim", "").replace('"', "'")
                final_prediction = text_item.get("finalPrediction")
                summary = text_item.get("summary", "").replace('"', "'")
                fix = text_item.get("fix", "").replace('"', "'")

                final_verdict = "Uncertain"
                if final_prediction is not None:
                    final_verdict = (
                        "Correct" if final_prediction == 1 else "Incorrect"
                    )

                if final_verdict == "Incorrect":
                    confidence = round(
                        (1 - (text_item.get("finalScore") or 0)) * 100, 2
                    )
                else:
                    confidence = round(
                        (text_item.get("finalScore") or 0) * 100, 2
                    )

                supporting_evidence = []
                refuting_evidence = []

                for evidence in evidence_list:
                    label = evidence.get("labelDescription", "")
                    if label not in ["SUPPORTS", "REFUTES"]:
                        continue

                    evidence_entry = {
                        "labelDescription": label,
                        "reliability": evidence.get(
                            "domain_reliability", {}
                        ).get("Reliability", "Unknown"),
                        "url": evidence.get("url", ""),
                    }

                    if label == "SUPPORTS":
                        supporting_evidence.append(evidence_entry)
                    else:
                        refuting_evidence.append(evidence_entry)

                cleaned_results.append(
                    {
                        "claim": claim_text,
                        "verdict": final_verdict,
                        "confidence_percentage": confidence,
                        "summary": summary,
                        "fix": fix,
                        "supporting_evidence": supporting_evidence,
                        "refuting_evidence": refuting_evidence,
                    }
                )

        return cleaned_results

    except Exception as e:
        logger.error(f"Error cleaning facts: {str(e)}")
        return []


async def claim_search():
    """Search for fact checking resources related to a given claim.

    Args:
        text: Text or claim to search for fact checks about

    Returns:
        Dictionary containing claim search results with format:

    Raises:
        HTTPException: When API call fails or service is unavailable
    """
    payload = {
        "logging": False,
        "lang": "en",
        "query": "",
        "reverseSortPubDate": True,
        "size": 100,
    }

    headers = {
        "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries + 1):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
                response = await client.post(
                    f"{API_BASE_URL}/claim_search",
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            if attempt < max_retries and e.response.status_code >= 500:
                print(
                    f"Retry attempt {attempt + 1}/{max_retries} for 5xx error"
                )
                await asyncio.sleep(retry_delay * (2**attempt))
                continue
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Claim search service error: {e.response.text}",
            )
        except httpx.RequestError as e:
            if attempt < max_retries:
                print(
                    f"Retry attempt {attempt + 1}/{max_retries} for "
                    "connection error"
                )
                await asyncio.sleep(retry_delay * (2**attempt))
                continue
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable: {str(e)}",
            )

    return None


def clean_claim_search_results(json_data: dict | None) -> list:
    """Extract and structure relevant claim search results.

    Args:
        json_data: The raw JSON response from the claim search API

    Returns:
        A list of cleaned and structured fact check result entries
    """
    cleaned_results: list[dict] = []

    if json_data is None or "searchResults" not in json_data:
        return cleaned_results

    for result in json_data.get("searchResults", []):
        claim = result.get("claim")
        label = result.get("label")

        if len(cleaned_results) == 3:
            break

        if (
            not claim
            or not label
            or any(
                word in claim.lower() for word in ["photo", "video", "image"]
            )
            or label == "unknown"
            or not result.get("domain")
        ):
            continue

        fact_check_entry = {
            "claim": result.get("claim", ""),
            "domain": result.get("domain", ""),
        }

        cleaned_results.append(fact_check_entry)

    return cleaned_results
