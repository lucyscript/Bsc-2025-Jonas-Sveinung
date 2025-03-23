"""Fact-checking utility for verifying claims using Factiverse API."""

import asyncio
import logging
import os
from typing import Any, Dict, List

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


async def batch_stance_detection(claims: List[str]) -> List[Dict[str, Any]]:
    """Process multiple claims concurrently using stance detection.

    Args:
        claims: List of claims to fact check

    Returns:
        List of stance detection results, one for each claim
    """
    if not claims:
        return []

    tasks = [stance_detection(claim) for claim in claims]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed_results: List[Dict[str, Any]] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(
                f"Error in batch processing claim '{claims[i]}': {str(result)}"
            )
            processed_results.append({"error": str(result), "claim": claims[i]})
        elif isinstance(result, dict):
            processed_results.append(result)
        else:
            logger.error(
                "Unexpected result type for claim "
                f"'{claims[i]}': {type(result)}"
            )
            processed_results.append(
                {
                    "error": f"Unexpected result type: {type(result)}",
                    "claim": claims[i],
                }
            )

    return processed_results


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
                logger.info(cleaned_results)
                return cleaned_results
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

                sim_score = evidence.get("simScore", 0)
                if sim_score > 0.5:
                    evidence_snippet = (
                        evidence.get("evidenceSnippet", "")[:1000] + "..."
                        if len(evidence.get("evidenceSnippet", "")) > 1000
                        else evidence.get("evidenceSnippet", "")
                    )
                else:
                    evidence_snippet = ""

                evidence_entry = {
                    "labelDescription": label,
                    "domain_name": evidence.get("domainName", ""),
                    "domainReliability": evidence.get(
                        "domain_reliability", {}
                    ).get("Reliability", "Unknown"),
                    "url": evidence.get("url", ""),
                    "evidenceSnippet": evidence_snippet,
                }

                if label == "SUPPORTS":
                    supporting_evidence.append(evidence_entry)
                else:
                    refuting_evidence.append(evidence_entry)

            if not summary and not fix:
                cleaned_results.append(
                    {
                        "strict_formatting": f"""
                        IMPORTANT:
                        DO NOT PROVIDE ANY ANALYSIS OR ELABORATION ON THE CLAIM.
                        YOU MUST RESPOND IDENTICAL TO THE IDENTICAL PART,
                        AND YOU MUST RESPOND NATURALLY TO THE NATURAL PART:

                        --- IDENTICAL ---
                        Claim: {claim_text}
                        Verdict: {final_verdict} ({confidence}% confidence)
                        --- IDENTICAL ---

                        --- NATURAL ---
                        URL AND EVIDENCE SNIPPET SUMMARY ONLY (MAX 3):
                        - Supporting Evidence: {supporting_evidence} sources
                        - Refuting Evidence: {refuting_evidence} sources

                        Encouraging ending
                        --- NATURAL ---
                        """,
                    }
                )
            else:
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
                        "evidenceSnippet": (
                            evidence.get("evidenceSnippet", "")[:1000] + "..."
                            if len(evidence.get("evidenceSnippet", "")) > 1000
                            else evidence.get("evidenceSnippet", "")
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
                        "summary": summary,
                        "fix": fix,
                        "supporting_evidence": supporting_evidence,
                        "refuting_evidence": refuting_evidence,
                    }
                )

        logger.info(cleaned_results)

        return cleaned_results

    except Exception as e:
        logger.error(f"Error cleaning facts: {str(e)}")
        return []
