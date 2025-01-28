"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

from fastapi import FastAPI, Request, HTTPException
import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv()

# Create FastAPI app
app = FastAPI()

# Get token from environment variables
verify_token = os.getenv("WEBHOOK_VERIFY_TOKEN")

# Print for debugging
print(f"Loaded token: {verify_token}")


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}


# Define GET and POST methods for WhatsApp API
@app.get("/whatsapp")
async def whatsapp_get(request: Request):
    """Handle GET requests for WhatsApp webhook verification.

    This endpoint is used by WhatsApp to verify the webhook URL.

    Returns:
        dict: A simple response message
    """
    query_params = request.query_params
    mode = query_params.get("hub.mode")
    token = query_params.get("hub.verify_token")
    challenge = query_params.get("hub.challenge")

    if mode == "subscribe" and token == verify_token:
        return challenge
    else:
        raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/whatsapp")
async def whatsapp_post():
    """Handle POST requests from WhatsApp webhook.

    This endpoint receives messages and events from WhatsApp Cloud API.

    Returns:
        dict: A simple response message
    """
    return {"message": "Hello World"}
