"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

import logging

from fastapi import FastAPI

from src.whatsapp.routers import router as whatsapp_router

app = FastAPI()

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_app")

# Mount the WhatsApp routes
app.include_router(whatsapp_router)


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}
