"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

import logging

from fastapi import FastAPI

from src.db.routers import router as db_router
from src.whatsapp.routers import router as whatsapp_router

app = FastAPI()

logging.basicConfig(level=logging.INFO)

app.include_router(whatsapp_router)
app.include_router(db_router)


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}
