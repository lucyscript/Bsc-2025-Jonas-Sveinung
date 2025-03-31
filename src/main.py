"""FastAPI application for WhatsApp webhook integration and fact-checking.

This module sets up a FastAPI application that handles webhook verification and
message processing for WhatsApp Cloud API integration.
"""

import logging

from fastapi import FastAPI

from src.db.utils import connect, create_tables
from src.platform.telegram.routers import router as telegram_router
from src.platform.whatsapp.routers import router as whatsapp_router

app = FastAPI()

logging.basicConfig(level=logging.INFO)

app.include_router(whatsapp_router)
app.include_router(telegram_router)


@app.on_event("startup")
async def startup_db_client():
    """Initializes the database connection and creates tables."""
    try:
        conn = connect()
        create_tables(conn)
        conn.close()
    except Exception as e:
        logging.error(f"Failed to initialize database: {e}")


@app.get("/")
async def root():
    """Root endpoint for API health check.

    Returns:
        dict: A simple hello world message
    """
    return {"message": "Hello World"}
