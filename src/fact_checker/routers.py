"""Test."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/check")
async def fact_check(message: dict):
    """Dummy endpoint simulate fact-checking.

    Expected input JSON:
    {
        "text": "Content to fact-check",
        "language": "en",        # optional
        "context": "additional context"  # optional
    }
    """
    text = message.get("text", "")
    language = message.get("language", "en")
    context = message.get("context", "")

    # Simulate fact-check processing.
    # In a real implementation, you would call the external Factiverse API.
    mock_result = {
        "original_message": text,
        "fact_check_result": "This is a mock fact-check result",
        "confidence": 0.95,  # a mock confidence score
        "details": {
            "language_used": language,
            "context_received": context,
        },
    }
    return mock_result
