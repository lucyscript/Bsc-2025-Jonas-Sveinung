"""Fact-checking utility for verifying claims using Factiverse API."""

import asyncio
import json
import logging
import os

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from langdetect import detect

from src.config.prompts import get_prompt

load_dotenv()

API_BASE_URL = "https://dev.factiverse.ai/v1"
FACTIVERSE_API_TOKEN = os.getenv("FACTIVERSE_API_TOKEN")
REQUEST_TIMEOUT = 10

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
                content=json.dumps(payload),
                headers=headers,
            )
            response.raise_for_status()
            return response.json().get("full_output", "").replace("**", "*")

    except httpx.HTTPStatusError as e:
        print(
            f"HTTP Error: {e.request.url} | {e.response.status_code} | "
            f"{e.response.text}"
        )
        raise
    except Exception as e:
        print(f"Generate Error: {str(e)}")
        raise


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
        "logging": False,
        "claim": claim,
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
                    f"{API_BASE_URL}/stance_detection",
                    content=json.dumps(payload),
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
                detail=f"Fact check service error: {e.response.text}",
            )
        except httpx.RequestError as e:
            if attempt < max_retries:
                print(
                    f"Retry attempt {attempt + 1}/{max_retries} "
                    "for connection error"
                )
                await asyncio.sleep(retry_delay * (2**attempt))
                continue
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable: {str(e)}",
            )

    return None


async def fact_check(claims: list[str], url: str = ""):
    """Check factual accuracy of a text using Factiverse API.

    Args:
        claims: List of claims to fact check
        url: Optional source URL of the content

    Returns:
        FactCheckResult containing verdict and supporting evidence

    Raises:
        HTTPException: When API call fails or service is unavailable
    """
    payload = {
        "logging": False,
        "text": "",
        "claims": claims,
        "url": url,
        "lang": detect(claims[0]),
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
                    f"{API_BASE_URL}/fact_check",
                    content=json.dumps(payload),
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
                detail=f"Fact check service error: {e.response.text}",
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


async def detect_claims(text: str, threshold: float = 0.75) -> list[str]:
    """Detect individual claims in text using Factiverse API.

    Args:
        text: Text to check for claims
        threshold: Minimum confidence threshold for claims

    Returns:
        Claims detected in the text

    Raises:
        HTTPException: When API call fails or service is unavailable
    """
    lang = detect(text)

    payload = {
        "logging": False,
        "lang": lang,
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
                content=json.dumps(payload),
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

    if (
        "collection" in json_data
        and json_data["collection"] == "stance_detection"
    ):
        claim_text = json_data.get("claim", "")
        evidence_list = json_data.get("evidence", [])
        summary = json_data.get("summary", "")
        fix = json_data.get("fix", "")

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
                "domainReliability": evidence.get("domain_reliability", {}).get(
                    "Reliability", "Unknown"
                ),
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
        for claim in json_data.get("claims", []):
            claim_text = claim.get("claim", "")
            final_prediction = claim.get("finalPrediction")
            final_verdict = "Uncertain"
            if final_prediction is not None:
                final_verdict = (
                    "Correct" if final_prediction == 1 else "Incorrect"
                )

            if final_verdict == "Incorrect":
                confidence = round(
                    (1 - (json_data.get("finalScore") or 0)) * 100, 2
                )
            else:
                confidence = round((json_data.get("finalScore") or 0) * 100, 2)

            supporting_evidence = []
            refuting_evidence = []

            evidence_list = claim.get("evidence") or []
            for evidence in evidence_list:
                label = evidence.get("labelDescription", "")
                if label not in ["SUPPORTS", "REFUTES"]:
                    continue

                evidence_entry = {
                    "labelDescription": label,
                    "reliability": evidence.get("domain_reliability", {}).get(
                        "Reliability", "Unknown"
                    ),
                    "url": evidence.get("url", ""),
                    "evidence_snippet": (
                        evidence.get("evidenceSnippet", "")[:1000].replace(
                            '"', "'"
                        )
                        + "..."
                        if len(evidence.get("evidenceSnippet", "")) > 1000
                        else evidence.get("evidenceSnippet", "").replace(
                            '"', "'"
                        )
                    ),
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
                    "supporting_evidence": supporting_evidence,
                    "refuting_evidence": refuting_evidence,
                }
            )

    return cleaned_results


async def generate_response(
    evidence: list, message: str, context: str = ""
) -> str:
    """Process a single claim group through the generation pipeline."""
    try:
        message_text = message.strip()
        claims = [entry["claim"] for entry in evidence]
        lang = detect(claims[0]) if claims else detect(message_text)

        if not claims:
            response_prompt = get_prompt(
                "no_claims_response",
                lang=lang,
                message_text=message_text,
                context=context,
            )
            return await generate(response_prompt)

        response_prompt = get_prompt(
            "claims_response",
            lang=lang,
            message_text=message_text,
            context=context,
        )

        # JSON serialization with proper quote handling
        evidence_text = json.dumps(evidence, ensure_ascii=False)
        return await generate(response_prompt, evidence_text)

    except Exception as e:
        print(f"Group processing failed: {str(e)}")
        return ""
