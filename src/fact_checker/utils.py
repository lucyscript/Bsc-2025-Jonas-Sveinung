"""Fact-checking utility for verifying claims using Factiverse API."""

import json
import os
import asyncio

import httpx
from dotenv import load_dotenv
from fastapi import HTTPException

# Load environment variables
load_dotenv()

# Configuration
FACTIVERSE_API_TOKEN = os.getenv("FACTIVERSE_API_TOKEN")
if not FACTIVERSE_API_TOKEN:
    raise ValueError("FACTIVERSE_API_TOKEN not found in .env file")

API_BASE_URL = os.getenv("FACTIVERSE_API_URL", "https://dev.factiverse.ai/v1")
REQUEST_TIMEOUT = 10  # seconds


async def generate(text: str, prompt: str):
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

    enhanced_user_input = await contextualize_user_input(text)

    payload = {
        "logging": False,
        "text": enhanced_user_input,
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


async def contextualize_user_input(context: str) -> str:
    """Generate context for a given user input using Factiverse API."""
    prompt = """\nRephrase the input text into 5 definitive claims that strictly follow these rules:
    1. Use the EXACT terminology from the input
    2. Always maintain the original perspective and intent
    3. Formulate as complete, verifiable statements
    4. No counter-arguments or corrections
    5. Preserve controversial aspects
    6. Do not mention words that are tied to the corrected claim, such as "reflects that of [counter-claim]."
    7. Always auto detect language of the claim and write the rewritten claims in the detected language
    
    Example Input/Output:
    Input: "Covid man-made"
    Output: 
    1. Covid is a man-made virus created in a laboratory.
    2. The origins of Covid are tied to human manipulation rather than natural evolution.
    3. There is substantial evidence suggesting that Covid was engineered for specific purposes.
    4. The theory that Covid is man-made should be investigated more rigorously.
    5. Covid being man-made poses significant risks to public safety and global health.

    Input: "pegmatite is a sedimentary rock"
    Output:
    1. Pegmatite is a sedimentary rock formed through rapid cooling.
    2. Sedimentary processes create pegmatite formations.
    3. The composition of pegmatite matches typical sedimentary rocks.
    4. Pegmatite's crystal structure proves its sedimentary origins.
    5. Geological classification systems categorize pegmatite as sedimentary.

    Input: \"Norge mennesker\"\n
    Output: \"Norge har det største antallet mennesker i verden.\", 
    \"Norge har det minste antallet mennesker i verden.\", 
    \"Norge har det mest mangfoldige antallet mennesker i verden.\", 
    \"Norge har det mest homogene antallet mennesker i verden., 
    Norge har det mest progressive antallet mennesker i verden.

    Input:\n"""

    try:
        enhanced_input = await generate(context, prompt)

        # Clean and format response
        enhanced_input = enhanced_input.strip().strip('"')

        print(f"Enhanced input: {enhanced_input}")
        return enhanced_input

    except Exception as e:
        print(f"Context Error: {str(e)}")
        return f'"{context}"'


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
        for evidence in claim.get("evidence") or []:
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

        # Safe confidence calculation with null fallback
        confidence = (claim.get("finalScore") or 0) * 100

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
        # Convert results to properly formatted JSON string
        payload_text = json.dumps(results)

        # Convert JSON string back to Python objects
        parsed_data = json.loads(payload_text)

        # Extract claims from each entry
        claims = [entry["claim"] for entry in parsed_data if "claim" in entry]

        # Create WhatsApp formatting prompt
        response_prompt = f"""Prompt: 🌐📚 You are FactiBot - a cheerful, multi-lingual, emoji-friendly fact-checking assistant for WhatsApp! Your mission:
        1️⃣ Clearly state if the verdict of the claim is 🟢 Supported ('verdict': 'Correct'), 🟡 Uncertain ('verdict': 'Uncertain'), or 🔴 Refuted ('verdict': 'Incorrect') using emojis
        2️⃣ Give a claim summary quoting the original claim text clarifying the correct stance with confidence percentage, followed by a linebreak
        3️⃣💡Give a brief, conversational explanation using simple language, followed by a linebreak
        4️⃣ Present evidence as 📌 Bullet points (•) with one 🔗 clickable link for each evidence, followed by a linebreak
        5️⃣ Add relevant emojis to improve readability
        6️⃣ 📚 Keep responses under 300 words, and ensure linebreaks for clarity
        7️⃣ Always maintain neutral, encouraging tone
        8️⃣ 🔗 Use ONLY the provided fact-check data - never invent information or links. Provide 3 supporting links only.
        9️⃣ Always end with a single short and friendly, open-ended encouragement to challenge more claims that the user may have on the current topic of the claim.

        Other important guidelines:
            Always reqpond in the language of the claim(s) for the entierty of the response.
            Always respond in whatsapp-friendly syntax and tone.
            Highlight keywords in bold for emphasis.
            Ensure linebreak between each section for readability, and never use markdown formatting syntax.
            Ensure the claim status emoji (🟢/🟡/🔴) is correctly tied to the verdict of the claim.
            Ensure the confidence percentage is accurate and rounded to the second decimal place.
            Prioritize the claim that contain evidence and has the highest confidence percentage.
            Prioritize the english format if you are uncertain about the language of the claim and evidence.

        (IMPORTANT) Always respond to this prompt in the language as these claim(s): {claims}
        ---
        Language detection example (English):
            claim(s): ['Pegmatite is a sedimentary rock formed through rapid cooling.', 'The composition of pegmatite matches typical sedimentary rocks.']
            Response language: English
        ---
        Language detection example (Norwegian):
            Claim(s): ['Torsk er den eneste fisken som lever i havet langs norskekysten.']
            Response language: Norwegian
        ---
        English format: 
            [Claim status emoji (🟢/🟡/🔴)] [Supported/Uncertain/Refuted] ([Confidence%] confidence)
            (linebreak)
            💡 [Definitive verdict] [Brief context/qualifier]
            (linebreak)
            📌 *Evidence:*
            • [Emoji] [Brief snippet] 
            🔗 [FULL_URL]
            (linebreak)
            🔍 One short sentence closing encouragement with a concise, friendly invitation encouraging the user to share more claims on the topic of the claim.
        ---
        Norwegian format:
            [Emoji for påstandens status (🟢/🟡/🔴)] [Støttet/Usikkert/Avvist] ([Konfidens%] sikkerhet)
            (ny linje)
            💡 Endelig konklusjon: [Kort kontekst/kvalifisering]
            (ny linje)
            📌 *Bevis*:
            • [Emoji] [Kort sitat/sammendrag]
            🔗 [FULL_URL]
            (ny linje)
            🔍 Del gjerne flere påstander om [tema]!
        ---

        Here are the only facts and data you will rely on for generating the response (input):"""

        # Call generate with properly formatted inputs
        return await generate(text=payload_text, prompt=response_prompt)

    except Exception as e:
        print(f"Tailored response generation failed: {str(e)}")
        return "⚠️ Service temporarily unavailable. Please try again later!"
