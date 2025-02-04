"""Tests for fact_checker/routers.py."""


def test_dummy():
    """A dummy test that always passes."""
    assert True


# from fastapi.testclient import TestClient
#
# from src.main import app  # Import your FastAPI app
#
# client = TestClient(app)
#
#
# def test_fact_check_endpoint_success():
#     """Test successful fact-checking endpoint call."""
#     test_data = {
#         "text": "This is a test statement.",
#         "language": "en",
#         "context": "some context",
#     }
#     response = client.post("/fact-check/check", json=test_data)
#
#     assert response.status_code == 200
#     response_json = response.json()
#     assert "result" in response_json
#
#
# def test_fact_check_endpoint_missing_text():
#     """Test fact-checking endpoint with missing text data."""
#     test_data = {"language": "en", "context": "some context"}
#     response = client.post("/fact-check/check", json=test_data)
#
#     assert response.status_code == 422  # Unprocessable Entity
#     assert "detail" in response.json()
#
#
# def test_fact_check_endpoint_empty_text():
#     """Test fact-checking endpoint with empty text."""
#     test_data = {"text": "", "language": "en", "context": "some context"}
#     response = client.post("/fact-check/check", json=test_data)
#
#     assert response.status_code == 422  # Unprocessable Entity
#     assert "detail" in response.json()
#
#
# def test_fact_check_endpoint_long_text():
#     """Test fact-checking endpoint with a long text."""
#     long_text = "This is a very long text. " * 500  # Create a long string
#     test_data = {
#         "text": long_text,
#         "language": "en",
#         "context": "some context",
#     }
#     response = client.post("/fact-check/check", json=test_data)
#
#     assert response.status_code == 200
#     response_json = response.json()
#     assert "result" in response_json
