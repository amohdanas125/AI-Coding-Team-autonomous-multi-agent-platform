"""Tests for openai_client.py: call spacing, error handling, rate-limit retries,
and structured outputs validation. All offline with mocked OpenAI API calls.
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import openai_client
from schemas import GENERATED_FILE_SCHEMA, validate_payload


@patch("openai_client.time.sleep")
@patch("openai_client.time.time")
def test_enforce_call_spacing_waits_when_calls_too_close(mock_time, mock_sleep):
    openai_client._last_call_timestamp = None
    mock_time.side_effect = [100.0, 100.0, 100.2, 100.2]

    openai_client._enforce_call_spacing()
    openai_client._enforce_call_spacing()

    assert mock_sleep.call_count == 1
    assert abs(mock_sleep.call_args[0][0] - (openai_client.MIN_SECONDS_BETWEEN_CALLS - 0.2)) < 1e-5


@patch("openai_client.get_client")
def test_call_agent_succeeds_with_structured_output(mock_get_client):
    openai_client._last_call_timestamp = None
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({"path": "app.js", "content": "console.log(1);"})))
    ]
    mock_client.chat.completions.create.return_value = fake_response

    with patch("openai_client._enforce_call_spacing"):
        result = openai_client.call_agent(
            system_prompt="sys",
            user_prompt="usr",
            schema=GENERATED_FILE_SCHEMA,
            schema_name="generated_file",
        )

    validate_payload(result, GENERATED_FILE_SCHEMA)
    assert result["path"] == "app.js"
    assert "console.log" in result["content"]


@patch("openai_client.get_client")
def test_call_agent_retries_on_rate_limit(mock_get_client):
    openai_client._last_call_timestamp = None
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    class FakeRateLimit(Exception):
        status_code = 429

    fake_response = MagicMock()
    fake_response.choices = [
        MagicMock(message=MagicMock(content=json.dumps({"path": "test.js", "content": "// ok"})))
    ]
    mock_client.chat.completions.create.side_effect = [FakeRateLimit("Rate limit exceeded"), fake_response]

    with patch("openai_client.time.sleep"), patch("openai_client._enforce_call_spacing"):
        result = openai_client.call_agent(
            system_prompt="sys",
            user_prompt="usr",
            schema=GENERATED_FILE_SCHEMA,
            schema_name="generated_file",
        )

    assert result["path"] == "test.js"
    assert mock_client.chat.completions.create.call_count == 2
