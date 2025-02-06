"""Router for handling WhatsApp Cloud API webhook endpoints."""

from fastapi import APIRouter, Request, HTTPException
import httpx

router = APIRouter()

VERIFY_TOKEN = "your_verify_token_here"  # Replace with your own token


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str, hub_verify_token: str, hub_challenge: str
):
    """Mimic the WhatsApp webhook verification.

    WhatsApp sends hub.verify_token and hub.challenge in the query parameters.
    """
    if hub_verify_token != VERIFY_TOKEN:
        raise HTTPException(
            status_code=403, detail="Verification token mismatch"
        )
    return int(hub_challenge)


@router.post("/webhook")
async def receive_message(request: Request):
    """Handle incoming messages from WhatsApp.

    This stub extracts a text message (and optionally language/context) from the
    payload, calls the fact-checker endpoint with a properly structured payload,
    and returns the result.
    """
    payload = await request.json()
    text = payload.get("text", "")
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text' in payload")

    # Prepare a payload for the Factiverse (fact-checker) endpoint
    fact_payload = {
        "text": text,
        "language": payload.get("language", "en"),  # Default language
        "context": payload.get("context", ""),  # Optional additional context
    }

    # Call the mock fact-checker endpoint
    async with httpx.AsyncClient() as client:
        fact_response = await client.post(
            "http://127.0.0.1:8000/fact-checker/check", json=fact_payload
        )
        fact_response.raise_for_status()
        fact_result = fact_response.json()

    return {"status": "processed", "fact_check_result": fact_result}
