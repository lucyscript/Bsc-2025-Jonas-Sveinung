"""Tests for main.py."""

from code.main import app

from fastapi.testclient import TestClient

client = TestClient(app)


def test_read_main():
    """Test the main endpoint of the API."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Hello World"}


def test_whatsapp_get_success(monkeypatch):
    """Test successful WhatsApp webhook verification."""
    # Mock the verification token
    TEST_TOKEN = "test_verification_token"
    monkeypatch.setenv("WEBHOOK_VERIFY_TOKEN", TEST_TOKEN)

    # Set up test parameters that WhatsApp would send
    challenge = "test_challenge_string"
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": TEST_TOKEN,
        "hub.challenge": challenge,
    }

    # Make request with query parameters
    response = client.get("/whatsapp", params=params)

    # Verify response
    assert response.status_code == 200
    assert (
        response.text == challenge
    )  # PlainTextResponse returns text, not JSON


def test_whatsapp_get_wrong_token(monkeypatch):
    """Test webhook verification fails with wrong token."""
    # Mock the verification token
    TEST_TOKEN = "correct_token"
    monkeypatch.setenv("WEBHOOK_VERIFY_TOKEN", TEST_TOKEN)

    # Set up test parameters with wrong token
    params = {
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",  # Wrong token
        "hub.challenge": "test_challenge_string",
    }

    # Make request with query parameters
    response = client.get("/whatsapp", params=params)

    # Verify failure response
    assert response.status_code == 403
    assert response.json() == {"detail": "Verification failed"}


def test_whatsapp_get_wrong_mode(monkeypatch):
    """Test webhook verification fails with wrong mode."""
    # Mock the verification token
    TEST_TOKEN = "test_verification_token"
    monkeypatch.setenv("WEBHOOK_VERIFY_TOKEN", TEST_TOKEN)

    # Set up test parameters with wrong mode
    params = {
        "hub.mode": "wrong_mode",  # Wrong mode
        "hub.verify_token": TEST_TOKEN,
        "hub.challenge": "test_challenge_string",
    }

    # Make request with query parameters
    response = client.get("/whatsapp", params=params)

    # Verify failure response
    assert response.status_code == 403
    assert response.json() == {"detail": "Verification failed"}


def test_whatsapp_get_missing_params():
    """Test webhook verification fails with missing parameters."""
    # Make request with no parameters
    response = client.get("/whatsapp")

    # Verify failure response
    assert response.status_code == 403
    assert response.json() == {"detail": "Verification failed"}


def test_whatsapp_post_success():
    """Test successful POST with valid JSON webhook data."""
    webhook_data = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "123456789",
                "changes": [
                    {
                        "value": {
                            "messages": [
                                {"from": "123456789", "text": {"body": "Hello"}}
                            ]
                        }
                    }
                ],
            }
        ],
    }

    response = client.post("/whatsapp", json=webhook_data)
    assert response.status_code == 200
    assert response.json() == {"message": "Webhook received"}


def test_whatsapp_post_missing_object():
    """Test POST fails when 'object' field is missing."""
    webhook_data = {"entry": []}  # Missing 'object' field

    response = client.post("/whatsapp", json=webhook_data)
    assert response.status_code == 422  # Pydantic validation error
    assert "object" in response.text


def test_whatsapp_post_missing_entry():
    """Test POST fails when 'entry' field is missing."""
    webhook_data = {
        "object": "whatsapp_business_account"  # Missing 'entry' field
    }

    response = client.post("/whatsapp", json=webhook_data)
    assert response.status_code == 422
    assert "entry" in response.text


def test_whatsapp_post_invalid_json():
    """Test POST fails with invalid JSON."""
    # Send invalid JSON as bytes with proper content-type header
    response = client.post(
        "/whatsapp",
        headers={"Content-Type": "application/json"},
        content=b"not a json",
    )
    assert response.status_code == 422


def test_whatsapp_post_wrong_types():
    """Test POST fails when fields have wrong types."""
    webhook_data = {
        "object": 123,  # Should be string
        "entry": "not a list",  # Should be list
    }

    response = client.post("/whatsapp", json=webhook_data)
    assert response.status_code == 422
