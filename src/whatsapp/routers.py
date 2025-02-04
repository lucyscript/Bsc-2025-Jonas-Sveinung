"""Router for handling WhatsApp Cloud API webhook endpoints."""

from fastapi import APIRouter, Request, HTTPException, Query
import logging

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

VERIFY_TOKEN = "your_verify_token_here"


@router.get("")
async def verify_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
):
    """Verification endpoint for the WhatsApp Cloud API webhook.

    WhatsApp sends GET request with the following query parameters:
      - hub.mode
      - hub.verify_token
      - hub.challenge

    Otherwise, a 403 status is returned.
    """
    if hub_mode != "subscribe":
        raise HTTPException(
            status_code=403, detail="Invalid hub mode. Expected 'subscribe'."
        )
    if hub_verify_token != VERIFY_TOKEN:
        raise HTTPException(
            status_code=403, detail="Verification token mismatch."
        )
    return int(hub_challenge)


@router.post("")
async def receive_webhook(request: Request):
    """Receiver endpoint for WhatsApp Cloud API webhook events.

    This endpoint gets a POST request containing the webhook event payload,
    which you can process accordingly
    """
    try:
        payload = await request.json()
    except Exception as e:
        logging.error(f"Error parsing JSON payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Log the received payload for debugging.
    logging.info(f"Received WhatsApp webhook payload: {payload}")

    # Process the payload (e.g., handle incoming messages, status updates, etc.)
    # [Your processing logic goes here.]

    # Acknowledge receipt of the webhook event.
    return {"status": "success"}
