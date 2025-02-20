"""Fact-checking utility for verifying claims using Factiverse API."""

import json
import os
import asyncio
import re

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException
from langdetect import detect

# Load environment variables
load_dotenv()

# Configuration
FACTIVERSE_API_TOKEN = os.getenv("FACTIVERSE_API_TOKEN")
if not FACTIVERSE_API_TOKEN:
    raise ValueError("FACTIVERSE_API_TOKEN not found in .env file")

API_BASE_URL = os.getenv("FACTIVERSE_API_URL", "https://dev.factiverse.ai/v1")
REQUEST_TIMEOUT = 10  # seconds


async def generate(prompt: str, text="") -> str:
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
            return (
                response.json()
                .get("full_output")
                .replace("**", "*")  # Clean accidental markdown
            )

    except httpx.HTTPStatusError as e:
        print(
            f"HTTP Error: {e.request.url} | {e.response.status_code} | {e.response.text}"
        )
        raise
    except Exception as e:
        print(f"Generate Error: {str(e)}")
        raise


async def stance_detection(claim: str):
    """Check factual accuracy of a text using Factiverse API.

    Args:
        claim: Claim to fact check
        text: Text content to fact check
        url: Optional source URL of the content

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
    retry_delay = 1  # Initial delay in seconds

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
                await asyncio.sleep(
                    retry_delay * (2**attempt)
                )  # Exponential backoff
                continue
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Fact check service error: {e.response.text}",
            )
        except httpx.RequestError as e:
            if attempt < max_retries:
                print(
                    f"Retry attempt {attempt + 1}/{max_retries} for connection error"
                )
                await asyncio.sleep(
                    retry_delay * (2**attempt)
                )  # Exponential backoff
                continue
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable: {str(e)}",
            )

    # This return is theoretically unreachable but satisfies type checker
    return None


async def fact_check(claims: list[str], url: str = ""):
    """Check factual accuracy of a text using Factiverse API.

    Args:
        claim: Claim to fact check
        text: Text content to fact check
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
    retry_delay = 1  # Initial delay in seconds

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
                await asyncio.sleep(
                    retry_delay * (2**attempt)
                )  # Exponential backoff
                continue
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Fact check service error: {e.response.text}",
            )
        except httpx.RequestError as e:
            if attempt < max_retries:
                print(
                    f"Retry attempt {attempt + 1}/{max_retries} for connection error"
                )
                await asyncio.sleep(
                    retry_delay * (2**attempt)
                )  # Exponential backoff
                continue
            raise HTTPException(
                status_code=503,
                detail=f"Service temporarily unavailable: {str(e)}",
            )

    # This return is theoretically unreachable but satisfies type checker
    return None


async def detect_claims(text: str, threshold: float = 0.9) -> list[str]:
    """Detect individual claims in text using Factiverse API."""

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

            # Directly extract from top-level detectedClaims
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


# async def contextualize_user_input(context: str) -> list[str]:
#     """Generate context for a given user input using Factiverse API."""
#     lang = detect(context)
#     user_input = context.strip()

#     prompt = f"""Only if the message '{user_input}' contain verifiable and biased claims, then find and reprase them by strictly follow these rules:
#     1. Use the EXACT terminology from the input
#     2. Always maintain the original perspective and intent
#     3. Formulate as complete, verifiable statements
#     4. No counter-arguments or corrections
#     5. Preserve controversial aspects
#     6. Do not mention words that are tied to the corrected claim, such as 'reflects that of [counter-claim].'
#     7. Each claim must be entirely in {lang} - never mix languages within a claim
#     8. Claims must be atomic - no multiple sentences separated by newlines
#     9. Never include syntax like '\nIt is...' in claims
#     10. Always replace they, it, etc. with the contextual subject. E.g., Covid was man made, and they made it in a lab -> Covid was man made, Covid was made in a lab

#     Language Rules:
#         🌍 Always respond in the original language of the input text ({lang})
#         💬 Maintain colloquial expressions from the users language
#         🚫 Never mix languages in response, purely respond in {lang}

#     Example Input/Output:
#     Input: Covid man-made
#     Output:
#        Covid is a man-made virus created in a laboratory.

#     Input: Cracking your knuckles causes arthritis, and using a microwave makes food radioactive.
#     Output:
#         Cracking your knuckles causes arthritis
#         Using a microwave makes food radioactive.

#     Input: Norge mennesker
#     Output:
#         Norge har det største antallet mennesker i verden.

#     Input: Hello there!
#     Output:

#     Now make single claims based on this message: '{user_input}'"""

# try:
#     enhanced_input = await generate(
#         prompt=prompt)

#     # Improved cleaning with sentence splitting
#     claims = []
#     # Split by periods and handle potential ellipsis
#     for raw_claim in re.split(r'(?<!\.)\.(?!\.)\s*', enhanced_input):
#         claim = (
#             raw_claim.strip()
#             .strip('",.')  # Remove edge punctuation
#             .replace("\\n", " ")  # Remove newline markers
#             .replace("  ", " ")  # Fix double spaces
#         )

#         if claim:  # Only append non-empty claims
#             claims.append(claim)

#     return claims

# except Exception as e:
#     print(f"Context Error: {str(e)}")
#     return [f'"{context}"']


def clean_facts(json_data: dict) -> list:
    """Extract relevant fact-check results with dynamic evidence balancing."""
    cleaned_results = []

    # Handle stance detection response
    if "collection" in json_data and json_data["collection"] == "stance_detection":
        claim_text = json_data.get("claim", "")
        evidence_list = json_data.get("evidence", [])
        
        # Determine verdict based on finalPrediction
        final_verdict = "Uncertain"
        if json_data.get("finalPrediction") is not None:
            final_verdict = "Incorrect" if json_data.get("finalPrediction") == 0 else "Correct"

        # Process confidence with proper rounding
        if final_verdict == "Incorrect":
            confidence = round((1 - (json_data.get("finalScore") or 0)) * 100, 2)
        else:
            confidence = round(((json_data.get("finalScore") or 0)) * 100, 2)
        
        # Process evidence
        supporting_evidence = []
        refuting_evidence = []
        
        for evidence in evidence_list:
            label = evidence.get("labelDescription", "")
            if label not in ["SUPPORTS", "REFUTES"]:
                continue

            evidence_entry = {
                "evidenceSnippet": (
                    evidence.get("evidenceSnippet", "")[:1000] + "..."
                    if len(evidence.get("evidenceSnippet", "")) > 1000
                    else evidence.get("evidenceSnippet", "")
                ),
                "url": evidence.get("url", ""),
                "labelDescription": label,
                # "bias": evidence.get("domain_reliability", {})
                # .get("bias_data", {})
                # .get("bias", "Unknown"),
                "reliability": evidence.get("domain_reliability", {}).get(
                    "Reliability", "Unknown"
                ),
            }

            if label == "SUPPORTS":
                supporting_evidence.append(evidence_entry)
            else:
                refuting_evidence.append(evidence_entry)

        cleaned_results.append({
            "claim": claim_text,
            "verdict": final_verdict,
            "confidence_percentage": confidence,
            "supporting_evidence": supporting_evidence,
            "refuting_evidence": refuting_evidence,
        })

    # Handle fact check response (existing logic)
    else:
        for claim in json_data.get("claims", []):
            # Extract core claim information with null checks
            claim_text = claim.get("claim", "")
            final_prediction = claim.get("finalPrediction")
            final_verdict = "Uncertain"
            if final_prediction is not None:
                final_verdict = "Correct" if final_prediction == 1 else "Incorrect"

            if final_verdict == "Incorrect":
                confidence = round((1 - (json_data.get("finalScore") or 0)) * 100, 2)
            else:
                confidence = round(((json_data.get("finalScore") or 0)) * 100, 2)

            # Process evidence with empty list handling
            supporting_evidence = []
            refuting_evidence = []

            # Handle null/empty evidence list
            evidence_list = claim.get("evidence") or []
            for evidence in evidence_list:
                label = evidence.get("labelDescription", "")
                if label not in ["SUPPORTS", "REFUTES"]:
                    continue

                evidence_entry = {
                    "evidence_snippet": (
                        evidence.get("evidenceSnippet", "")[:1000] + "..."
                        if len(evidence.get("evidenceSnippet", "")) > 1000
                        else evidence.get("evidenceSnippet", "")
                    ),
                    "url": evidence.get("url", ""),
                    # "domain": evidence.get("domainName", "Unknown source"),
                    "labelDescription": label,
                    # "bias": evidence.get("domain_reliability", {})
                    # .get("bias_data", {})
                    # .get("bias", "Unknown"),
                    "reliability": evidence.get("domain_reliability", {}).get(
                        "Reliability", "Unknown"
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


# async def generate_tailored_response(results: list) -> str:
#     """Generate context-aware response based on fact-check results."""
#     try:
#         # Group claims before processing
#         #claim_groups = await group_claims(results)

#         separator = "\n━━━━━━━━━━\n"  # Horizontal line separator
#         all_responses = []
#         for group in claim_groups:
#             # Process each claim group separately
#             group_response = await process_claim_group(group)
#             if group_response:
#                 all_responses.append(group_response)

#         return separator.join(all_responses)

#     except Exception as e:
#         print(f"Tailored response generation failed: {str(e)}")
#         return "⚠️ Service temporarily unavailable. Please try again later!"


# async def group_claims(results: list) -> list:
#     """Group claims by shared keywords and themes."""
#     try:
#         claims = [entry["claim"] for entry in results]
#         print(claims)

#         # Improved noun detection pattern
#         noun_pattern = re.compile(
#             r"\b[A-Z][a-z]+\b|",
#             flags=re.UNICODE,
#         )
#         claim_keywords = []
#         for claim in claims:
#             nouns = set(
#                 word.lower()
#                 for word in noun_pattern.findall(claim)
#             )
#             claim_keywords.append(
#                 {"original": claim, "nouns": nouns, "group": -1}
#             )

#         # Cluster claims based on keyword overlap
#         current_group = 0
#         for i in range(len(claim_keywords)):
#             if claim_keywords[i]["group"] == -1:
#                 claim_keywords[i]["group"] = current_group
#                 for j in range(i + 1, len(claim_keywords)):
#                     if (
#                         claim_keywords[j]["group"] == -1
#                         and len(
#                             claim_keywords[i]["nouns"]
#                             & claim_keywords[j]["nouns"]
#                         )
#                         > 0
#                     ):
#                         claim_keywords[j]["group"] = current_group
#                 current_group += 1

#         # Create grouped results
#         grouped_results = {}
#         for ck, result in zip(claim_keywords, results):
#             group_id = ck["group"]
#             if group_id not in grouped_results:
#                 grouped_results[group_id] = []
#             grouped_results[group_id].append(result)

#         return list(grouped_results.values())

#     except Exception as e:
#         print(f"Grouping error: {str(e)}")
#         return [results]  # Fallback to single group


async def process_claim_group(group: list, message: str) -> str:
    """Process a single claim group through the generation pipeline."""
    try:
        message_text = message.strip()
        claims = [entry["claim"] for entry in group]
        group_text = json.dumps(group, indent=2)
        lang = detect(claims[0]) if claims else 'en'

        print(claims)

        # Helper functions must be defined inside the scope
        # def get_confidence_phrase(claims):
        #     max_conf = max(
        #         (
        #             100 - c["confidence_percentage"]
        #             if c["verdict"] == "Incorrect"
        #             else c["confidence_percentage"]
        #         )
        #         for c in claims
        #     )
        #     if max_conf > 80:
        #         return 'Strong indication'
        #     if max_conf > 60:
        #         return 'Current understanding suggests'
        #     return 'Available information hints'

        # def get_verdict_phrases(claims):
        #     phrases = []
        #     for claim in claims:
        #         emoji = {"Correct": "🟢", "Incorrect": "🔴", "Uncertain": "🟡"}[
        #             claim["verdict"]
        #         ]
        #         adj_conf = (
        #             100 - claim["confidence_percentage"]
        #             if claim["verdict"] == "Incorrect"
        #             else claim["confidence_percentage"]
        #         )
        #         phrases.append(
        #             f'{emoji} Regarding \"{claim['claim']}\" → {claim['verdict']} ({adj_conf:.1f}% confidence)'
        #         )
        #     return "\n".join(phrases)

        # # Build evidence text
        # evidence_text = []
        # for claim in group:
        #     evidence_type = (
        #         "supporting_evidence"
        #         if claim["verdict"] == "Correct"
        #         else "refuting_evidence"
        #     )
        #     for evidence in claim.get(evidence_type, []):
        #         evidence_snippet = (
        #             (evidence.get("evidenceSnippet", "")[:1000] + "...")
        #             if len(evidence.get("evidenceSnippet", "")) > 1000
        #             else evidence.get("evidenceSnippet", "")
        #         )
        #         evidence_text.append(
        #             f'• {evidence_snippet}\n  🔗 {evidence.get('url', '')}'
        #         )

        if claims == []:
            response_prompt = f"""You are a emoji-friendly fact-checking bot on WhatsApp that likes general conversation, and claim clarification.
        
                A whatsapp user just sent you a message: '{message_text}'

                Here are the rules you will follow to make up your reply:

                    Respond in the language of this languagecode: {lang}
                
                    Use linebreaks for readability

                    Always use plaintext to comply with WhatsApp text syntax

                    Never use markdown syntax

                    The only syntax you are allowed to use is * to make important words *bold* 

                    Keep the response short and concise

                    Never use hyphen -, use • instead 

                    Always reply in a conversational manner

                    End of with a contextualized open ended question

                    Always remain neutrual, regardless of the claims made in the message

                    Never provide any links or reference any sources regardless of what the message is 

                    Never use your search engine

                    Never correct the user regardless of what the message is and its claims
                """
            return await generate(prompt=response_prompt, text=group_text)

        response_prompt = f"""You are a emoji-friendly fact-checking bot on WhatsApp that likes general conversation, and claim clarification.
        
            A whatsapp user just sent you a message: '{message_text}'

            Here are the rules you will follow to make up your reply:

                Respond in the language of this languagecode: {lang}
                
                Use linebreaks for readability

                You must mention the verdict of each claim
                
                You must mention the confidence percentage for each claim, and play it off as it is you that is this confident
                
                You must reference all full urls on a newline (with emoji 🔗) of the evidence snippets you decide to rely on in your response for each claim

                Never use syntax like [Domain](https://www.link.com)  
                
                Always use plaintext to comply with WhatsApp text syntax

                Never use markdown syntax

                The only syntax you are allowed to use is * to make important words *bold* 

                Keep the response short and concise

                Never use hyphen -, use • instead 

                Always reply in a conversational manner

                End of with a contextualized open ended question

            Here is everything you will rely on:"""

        return await generate(prompt=response_prompt, text=group_text)

    except Exception as e:
        print(f"Group processing failed: {str(e)}")
        return ""
