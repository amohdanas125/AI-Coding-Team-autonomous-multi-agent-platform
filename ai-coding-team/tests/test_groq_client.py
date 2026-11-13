"""Tests for groq_client.py's own logic - the call-spacing and retry
behavior that every agent depends on. Doesn't touch the network: patches
time.sleep/time.time so these run instantly."""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import groq_client


@patch("groq_client.time.sleep")
@patch("groq_client.time.time")
def test_enforce_call_spacing_waits_when_calls_are_close_together(mock_time, mock_sleep):
    groq_client._last_call_timestamp = None  # reset shared module state before the test
    # Each call to _enforce_call_spacing() reads time.time() twice: once to
    # check elapsed time, once to update the stored timestamp afterward.
    # Call 1 at t=100 (no previous timestamp, no wait). Call 2's "now" at
    # t=105 - only 5s after call 1's stored timestamp, less than the minimum.
    mock_time.side_effect = [100.0, 100.0, 105.0, 105.0]

    groq_client._enforce_call_spacing()
    groq_client._enforce_call_spacing()

    mock_sleep.assert_called_once_with(groq_client.MIN_SECONDS_BETWEEN_CALLS - 5.0)


@patch("groq_client.time.sleep")
@patch("groq_client.time.time")
def test_enforce_call_spacing_does_not_wait_when_calls_are_already_spread_out(mock_time, mock_sleep):
    groq_client._last_call_timestamp = None
    # Call 1 at t=100, call 2's "now" at t=200 - 100s apart, well over the minimum.
    mock_time.side_effect = [100.0, 100.0, 200.0, 200.0]

    groq_client._enforce_call_spacing()
    groq_client._enforce_call_spacing()

    mock_sleep.assert_not_called()


@patch("groq_client.get_client")
def test_call_agent_retries_on_rate_limit_then_succeeds(mock_get_client):
    groq_client._last_call_timestamp = None

    class FakeRateLimitError(Exception):
        status_code = 413

    fake_response = type("R", (), {
        "choices": [type("C", (), {"message": type("M", (), {"content": '{"ok": true}'})()})()]
    })()

    mock_client = mock_get_client.return_value
    mock_client.chat.completions.create.side_effect = [FakeRateLimitError("too large"), fake_response]

    with patch("groq_client.time.sleep"), patch("groq_client._enforce_call_spacing"):
        result = groq_client.call_agent(
            system_prompt="sys", user_prompt="usr",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"], "additionalProperties": False},
            schema_name="test_schema",
        )

    assert result == {"ok": True}
    assert mock_client.chat.completions.create.call_count == 2


@patch("groq_client.get_client")
def test_call_agent_retries_on_malformed_json_with_short_backoff(mock_get_client):
    # Distinct failure mode from rate limiting - Groq's own schema
    # validator rejecting a response whose JSON string-escaping got
    # corrupted mid-generation (seen live on a deeply nested schema).
    # Confirms this path is retried too, and specifically with the SHORT
    # 3s backoff (not rate limiting's 20s/40s) - see call_agent's comment
    # on why these get different wait times.
    groq_client._last_call_timestamp = None

    class FakeMalformedJsonError(Exception):
        status_code = 400
        def __str__(self):
            return "Error: json_validate_failed - the model output didn't match the schema"

    fake_response = type("R", (), {
        "choices": [type("C", (), {"message": type("M", (), {"content": '{"ok": true}'})()})()]
    })()

    mock_client = mock_get_client.return_value
    mock_client.chat.completions.create.side_effect = [FakeMalformedJsonError(), fake_response]

    with patch("groq_client.time.sleep") as mock_sleep, patch("groq_client._enforce_call_spacing"):
        result = groq_client.call_agent(
            system_prompt="sys", user_prompt="usr",
            schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"], "additionalProperties": False},
            schema_name="test_schema",
        )

    assert result == {"ok": True}
    assert mock_client.chat.completions.create.call_count == 2
    mock_sleep.assert_called_once_with(3)  # short backoff, not rate-limit's 20s


@patch("groq_client.get_client")
def test_call_agent_does_not_retry_on_unrelated_errors(mock_get_client):
    # A genuine, unrecoverable error (e.g. an auth failure) should raise
    # immediately, not burn through retries waiting for something that
    # will never resolve itself.
    groq_client._last_call_timestamp = None

    class FakeAuthError(Exception):
        status_code = 401

    mock_client = mock_get_client.return_value
    mock_client.chat.completions.create.side_effect = FakeAuthError("invalid api key")

    with patch("groq_client.time.sleep") as mock_sleep, patch("groq_client._enforce_call_spacing"):
        try:
            groq_client.call_agent(
                system_prompt="sys", user_prompt="usr",
                schema={"type": "object", "properties": {"ok": {"type": "boolean"}},
                        "required": ["ok"], "additionalProperties": False},
                schema_name="test_schema",
            )
            assert False, "expected FakeAuthError to propagate"
        except FakeAuthError:
            pass

    mock_sleep.assert_not_called()
    assert mock_client.chat.completions.create.call_count == 1
