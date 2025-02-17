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


async def generate(
    text: str, prompt: str, lang: str = "en", threshold: float = 0.9
) -> str:
    """Generate context for a given claim using Factiverse API."""
    payload = {
        "logging": False,
        "text": text,
        "prompt": prompt,
        "lang": lang,
        "threshold": threshold,
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


async def fact_check(claims: list[str], text: str, url: str = ""):
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
        "text": text,
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


# async def detect_claims(text: str, threshold: float = 0.9) -> list[str]:
#     """Detect individual claims in text using Factiverse API."""

#     enhanced_user_input = await contextualize_user_input(text)

# payload = {
#     "logging": False,
#     "text": text,
#     "claimScoreThreshold": threshold,
# }

# headers = {
#     "Authorization": f"Bearer {FACTIVERSE_API_TOKEN}",
#     "Content-Type": "application/json",
# }

# try:
#     async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
#         response = await client.post(
#             f"{API_BASE_URL}/claim_detection",
#             content=json.dumps(payload),
#             headers=headers,
#         )
#         response.raise_for_status()

#         claims_data = response.json()
# claims = []

# # Directly extract from top-level detectedClaims
# if "detectedClaims" in claims_data:
#     for claim in claims_data["detectedClaims"]:
#         claim_text = str(claim.get("claim", "")).strip()
#         if claim_text:
#             claims.append(claim_text)

# return claims

# except httpx.HTTPStatusError as e:
#     print(f"Claim detection API error: {str(e)}")
#     return []
# except KeyError as e:
#     print(f"Missing expected field in response: {str(e)}")
#     return []
# except Exception as e:
#     print(f"Error processing claims: {str(e)}")
#     return []


async def contextualize_user_input(
    context: str, threshold: float = 0.9
) -> list[str]:
    """Generate context for a given user input using Factiverse API."""
    lang = detect(context)

    prompt = """Rephrase the input text into 5 definitive claims that strictly follow these rules:
    1. Use the EXACT terminology from the input
    2. Always maintain the original perspective and intent
    3. Formulate as complete, verifiable statements
    4. No counter-arguments or corrections
    5. Preserve controversial aspects
    6. Do not mention words that are tied to the corrected claim, such as 'reflects that of [counter-claim].'
    7. Each claim must be entirely in {lang} - never mix languages within a claim
    8. Claims must be atomic - no multiple sentences separated by newlines
    9. Never include language codes like '\\nIt...' in claims

    Language Rules:
        🌍 Always respond in the original language of the input text ({lang})
        💬 Maintain colloquial expressions from the users language
        🚫 Never mix languages in response, purely respond in {lang}
    
    Example Input/Output:
    Input: Covid man-made
    Output: 
       Covid is a man-made virus created in a laboratory.,
       The origins of Covid are tied to human manipulation rather than natural evolution.,
       There is substantial evidence suggesting that Covid was engineered for specific purposes.,
       The theory that Covid is man-made should be investigated more rigorously.,
       Covid being man-made poses significant risks to public safety and global health.

    Input: pegmatite is a sedimentary rock
    Output:
       Pegmatite is a sedimentary rock formed through rapid cooling.,
       Sedimentary processes create pegmatite formations.,
       The composition of pegmatite matches typical sedimentary rocks.,
       Pegmatite's crystal structure proves its sedimentary origins.,
       Geological classification systems categorize pegmatite as sedimentary.

    Input: Norge mennesker
    Output: 
        Norge har det største antallet mennesker i verden., 
        Norge har det minste antallet mennesker i verden., 
        Norge har det mest mangfoldige antallet mennesker i verden., 
        Norge har det mest homogene antallet mennesker i verden., 
        Norge har det mest progressive antallet mennesker i verden.

    Input:"""

    try:
        enhanced_input = await generate(
            text=context,
            prompt=prompt.format(lang=lang),
            lang=lang,
            threshold=threshold,
        )

        # Improved cleaning with language consistency check
        claims = []
        for raw_claim in re.split(r"[\n,]+", enhanced_input):
            claim = (
                raw_claim.strip()
                .strip('",.')  # Remove edge punctuation
                .replace("\\n", " ")  # Remove newline markers
                .replace("  ", " ")  # Fix double spaces
            )

            # Verify claim language matches context
            if claim and detect(claim) == lang:
                claims.append(claim)

        return claims[:5]  # Return first 5 valid claims

    except Exception as e:
        print(f"Context Error: {str(e)}")
        return [f'"{context}"']


def clean_facts(json_data: dict) -> list:
    """Extract relevant fact-check results for tailored response."""
    cleaned_results = []

    for claim in json_data.get("claims", []):
        # Extract core claim information with null checks
        claim_text = claim.get("claim", "")
        final_prediction = claim.get("finalPrediction")
        final_verdict = "Uncertain"
        if final_prediction is not None:
            final_verdict = "Correct" if final_prediction == 1 else "Incorrect"

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
                "snippet": (
                    evidence.get("evidenceSnippet", "")[:1000] + "..."
                    if len(evidence.get("evidenceSnippet", "")) > 1000
                    else evidence.get("evidenceSnippet", "")
                ),
                "url": evidence.get("url", ""),
                "domain": evidence.get("domainName", "Unknown source"),
                "label": label,
            }

            if label == "SUPPORTS":
                supporting_evidence.append(evidence_entry)
            else:
                refuting_evidence.append(evidence_entry)

        # Process confidence with proper rounding
        confidence = round(
            (claim.get("finalScore") or 0) * 100, 2
        )  # Round to 2 decimals

        cleaned_results.append(
            {
                "claim": claim_text,
                "verdict": final_verdict,
                "confidence_percentage": confidence,
                "supporting_evidence": supporting_evidence[:3],
                "refuting_evidence": refuting_evidence[:1],
            }
        )

    return cleaned_results


async def generate_tailored_response(results: list) -> str:
    """Generate context-aware response based on fact-check results."""
    try:
        # Group claims before processing
        claim_groups = await group_claims(results)

        separator = "\n━━━━━━━━━━\n"  # Horizontal line separator
        all_responses = []
        for group in claim_groups:
            # Process each claim group separately
            group_response = await process_claim_group(group)
            if group_response:
                all_responses.append(group_response)

        return separator.join(all_responses)

    except Exception as e:
        print(f"Tailored response generation failed: {str(e)}")
        return "⚠️ Service temporarily unavailable. Please try again later!"


async def group_claims(results: list) -> list:
    """Group claims by shared keywords and themes."""
    try:
        claims = [entry["claim"] for entry in results]
        lang = detect(claims[0]) if claims else "en"

        # Extract nouns and proper nouns from claims
        noun_pattern = re.compile(
            r"\b[A-Z][a-z]+|\b\w+ing\b|\b\w+s\b", flags=re.IGNORECASE
        )
        claim_keywords = []

        for claim in claims:
            nouns = set(noun_pattern.findall(claim))
            claim_keywords.append(
                {"original": claim, "nouns": nouns, "group": -1}
            )

        # Cluster claims based on keyword overlap
        current_group = 0
        for i in range(len(claim_keywords)):
            if claim_keywords[i]["group"] == -1:
                claim_keywords[i]["group"] = current_group
                for j in range(i + 1, len(claim_keywords)):
                    if (
                        claim_keywords[j]["group"] == -1
                        and len(
                            claim_keywords[i]["nouns"]
                            & claim_keywords[j]["nouns"]
                        )
                        > 0
                    ):
                        claim_keywords[j]["group"] = current_group
                current_group += 1

        # Create grouped results
        grouped_results = {}
        for ck, result in zip(claim_keywords, results):
            group_id = ck["group"]
            if group_id not in grouped_results:
                grouped_results[group_id] = []
            grouped_results[group_id].append(result)

        return list(grouped_results.values())

    except Exception as e:
        print(f"Grouping error: {str(e)}")
        return [results]  # Fallback to single group


async def process_claim_group(group: list) -> str:
    """Process a single claim group through the generation pipeline."""
    try:
        payload_text = json.dumps(group)
        claims = [entry["claim"] for entry in group]
        lang = detect(claims[0]) if claims else "en"

        # Simplified prompt focused on single group
        response_prompt = f"""Prompt: 🌐📚 You are FactiBot - a cheerful, emoji-friendly fact-checking assistant for WhatsApp! Your mission:
        1️⃣ Clearly state if the verdict of the claim is 🟢 Supported ('verdict': 'Correct'), 🟡 Uncertain ('verdict': 'Uncertain'), or 🔴 Refuted ('verdict': 'Incorrect') using emojis, and ensure you are tranlating it to the language of this language code: {lang}
        2️⃣ Give a claim summary quoting the original claim text clarifying the correct stance with confidence percentage, followed by a linebreak
        3️⃣💡Give a brief, conversational explanation using simple language, followed by a linebreak
        4️⃣ Present evidence as 📌 Bullet points (•) with one 🔗 clickable link for each evidence, followed by a linebreak
        5️⃣ Add relevant emojis to improve readability
        6️⃣ 📚 Keep responses under 300 words, and ensure linebreaks for clarity. 
        7️⃣ Always maintain neutral, encouraging tone. Also, always respond in the language of this language code: {lang}
        8️⃣ 🔗 Use ONLY the provided fact-check data - never invent information or links. Provide 3 supporting links only. If no links are available, do not invent them, and do not provide any confident fact-checking
        9️⃣ Always end with a single short and friendly, open-ended encouragement to challenge more claims that the user may have on the current topic of the claim.

        Other important guidelines:
            Always respond in whatsapp-friendly syntax and tone.
            Highlight keywords in bold for emphasis.
            Ensure linebreak between each section for readability, and never use markdown formatting syntax.
            Ensure the claim status emoji (🟢/🟡/🔴) is correctly tied to the verdict of the claim.
            Ensure the confidence percentage is accurate and rounded to the second decimal place.
            Prioritize the claim that contain evidence and has the highest confidence percentage.
            Ensure the format is tranlated to the language of this language code: {lang}

            Language Rules:
                🌍 Always respond in the original language of the claim, which is represented by this language code: {lang}
                💬 Maintain colloquial expressions from the users language
                🚫 Never mix languages in response, purely respond in the language of this language code: {lang}

        Format to follow (ensure everything in bracets [] will be in the language of this language code: {lang}): 
            [Claim status emoji (🟢/🟡/🔴)] [Supported/Uncertain/Refuted (translate to the language of this language code: {lang})] ([Confidence%] confidence (translate to the language of this language code: {lang}))
            (linebreak)
            💡 [Definitive verdict] [Brief context/qualifier]
            (linebreak)
            📌 *Evidence (tranlate the word Evidence to the language of the language code {lang}):*
            • [Emoji] [Brief snippet] 
            🔗 [FULL_URL (do not translate the language of the url)]
            (linebreak)
            🔍 [One short sentence closing encouragement with a concise, friendly invitation encouraging the user to share more claims on the topic of the claim. ({lang})]

        Here are the only facts and data you will rely on for generating the response (input):"""

        return await generate(
            text=payload_text, prompt=response_prompt, lang=lang
        )

    except Exception as e:
        print(f"Group processing failed: {str(e)}")
        return ""
