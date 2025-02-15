"""Fact-checking utility for verifying claims using Factiverse API."""

import json
import os

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
REQUEST_TIMEOUT = 30  # seconds


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
                .get("full_output", "Summary unavailable")
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
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Fact check service error: {e.response.text}",
        )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f"Service temporarily unavailable: {str(e)}"
        )


async def detect_claims(text: str) -> list[str]:
    """Detect individual claims in text using Factiverse API."""

    enhanced_user_input = await contextualize_user_input(text)

    payload = {
        "logging": False,
        "text": enhanced_user_input,
        "claimScoreThreshold": 0.9,
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
    prompt = """Rephrase the following input text into 5 definitive claim,
        statement, or opinion. The claim should express a strong viewpoint or
        assertion about the subject, maintaining the language of the input text.
        The claim will later be verified with other tools. Consider the
        'Previous Claims' when rephrasing the 'Current Claim' to provide more
        specific and relevant context for fact-checking.\n\nExample Inputs and
        Outputs:\n• Input: \"climate change\"\nOutput: \"Climate change is a
        hoax.\", \"Climate change is a conspiracy theory.\", \"Climate change is
        a natural phenomenon.\", \"Climate change is a global threat.\",
        \"Climate change is a scientific fact.\"\n• Input: \"artificial
        intelligence\"\nOutput: \"Artificial intelligence will surpass human
        intelligence within a decade.\", \"Artificial intelligence is the future
        of technology.\", \"Artificial intelligence poses a threat to humanity.
        \", Artificial intelligence is revolutionizing industries.\",
        \"Artificial intelligence is a double-edged sword.\"\n• Input: \"Norge
        mennesker\"\nOutput: \"Norge har det største antallet mennesker i
        verden.\", \"Norge har det minste antallet mennesker i verden.\",
        \"Norge har det mest mangfoldige antallet mennesker i verden.\",
        \"Norge har det mest homogene antallet mennesker i verden., Norge har
        det mest progressive antallet mennesker i verden.\"\n\nInput:\n":"""
    try:
        enhanced_input = await generate(context, prompt)

        # Clean and format response
        enhanced_input = enhanced_input.strip().strip('"')

        print(enhanced_input)

        return enhanced_input

    except Exception as e:
        print(f"Context Error: {str(e)}")
        return f'"{context}"'


def clean_facts(json_data: dict) -> list:
    """Extract relevant fact-check results for tailored response."""
    cleaned_results = []

    for claim in json_data.get("claims", []):
        # Extract core claim information
        claim_text = claim.get("claim", "")
        final_verdict = (
            "Correct" if claim.get("finalPrediction") == 1 else "Incorrect"
        )

        # Process evidence
        supporting_evidence = []
        refuting_evidence = []

        for evidence in claim.get("evidence", []):
            label = evidence.get("labelDescription", "")
            if label not in ["SUPPORTS", "REFUTES"]:
                continue

            evidence_entry = {
                "snippet": (
                    evidence.get("evidenceSnippet", "")[:500] + "..."
                    if len(evidence.get("evidenceSnippet", "")) > 500
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

        # Calculate confidence score
        confidence = claim.get("finalScore", 0) * 100  # Convert to percentage

        cleaned_results.append(
            {
                "claim": claim_text,
                "verdict": final_verdict,
                "confidence_percentage": confidence,
                "supporting_evidence": supporting_evidence[
                    :3
                ],  # Top 3 supporting
                "refuting_evidence": refuting_evidence[
                    :1
                ],  # Top refuting if exists
            }
        )

    print(cleaned_results)

    return cleaned_results


async def generate_tailored_response(results: list) -> str:
    """Generate context-aware response based on fact-check results."""
    try:
        # Convert results to properly formatted JSON string
        payload_text = json.dumps(results)

        # Create WhatsApp formatting prompt
        response_prompt = """🌐📚 You are FactiBot - a cheerful, emoji-friendly fact-checking assistant for WhatsApp! Your mission:
        1️⃣ Clearly state if the claim is 🟢 Supported or 🔴 Refuted using emojis
        2️⃣ Give a claim summary quoting the original claim text clarifying the correct stance with confidence percentage
        3️⃣💡Give a brief, conversational explanation using simple language
        4️⃣ Present evidence as 📌 Bullet points with one 🔗 clickable link for each evidence
        5️⃣ Add relevant emojis to improve readability
        6️⃣ 📚 Keep responses under 300 words
        7️⃣ Always maintain neutral, encouraging tone
        8️⃣ 🔗 Use ONLY the provided fact-check data - never invent information or links. Provide 3 supporting links only with linebreaks between each evidence.
        9️⃣ Always end with a single short and friendly, open-ended encouragement to challenge more claims that the user may have on this topic

        Always respond in whatsapp-friendly syntax and tone, with no markdown.
        Highlight keywords in bold for emphasis.

        Format:
        [Claim status emoji (🟢/🔴)] [Refuted/Supported] ([Confidence%] confidence)
        (linebreak)
        💡 [Definitive verdict] [Brief context/qualifier]
        (linebreak)
        📚 Supporting Evidence:
        - [Emoji] [Brief snippet] 
        🔗 [FULL_URL]
        (linebreak)
        [Emoji] One short sentence closing encouragement with a concise, friendly invitation encouraging the user to share more claims on this topic.
        
        Here are the only facts and data you will rely on for generating the response:"""

        # Call generate with properly formatted inputs
        return await generate(text=payload_text, prompt=response_prompt)

    except Exception as e:
        print(f"Tailored response generation failed: {str(e)}")
        return "⚠️ Service temporarily unavailable. Please try again later!"
