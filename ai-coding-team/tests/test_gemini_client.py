"""Tests for gemini_client.py's own logic - call spacing, schema
conversion, response parsing, and retry-on-rate-limit. Doesn't touch the
network: patches time.sleep/time.time and the Gemini client so these run
instantly and without an API key.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gemini_client

TEST_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def _fake_response(text, thoughts=0, output=0):
    return type("R", (), {
        "text": text,
        "candidates": [type("Cand", (), {"finish_reason": "STOP"})()],
        "usage_metadata": type("U", (), {
            "thoughts_token_count": thoughts, "candidates_token_count": output,
        })(),
    })()


def test_to_gemini_schema_strips_additional_properties_recursively():
    nested = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": False, "properties": {}},
            }
        },
    }

    converted = gemini_client._to_gemini_schema(nested)

    assert "additionalProperties" not in converted
    assert "additionalProperties" not in converted["properties"]["items"]["items"]


def test_to_gemini_schema_does_not_mutate_the_original():
    original = {"type": "object", "additionalProperties": False, "properties": {}}
    original_copy = dict(original)

    gemini_client._to_gemini_schema(original)

    assert original == original_copy  # untouched - other call sites share this object


@patch("gemini_client.time.sleep")
@patch("gemini_client.time.time")
def test_enforce_call_spacing_waits_when_calls_are_close_together(mock_time, mock_sleep):
    gemini_client._last_call_timestamp = None
    # Gemini's spacing is much shorter than Groq's (5s vs 15s) - free tier
    # is RPM-gated, not a hard per-request token ceiling, so less spacing
    # is needed. 2s apart here is still under that 5s minimum.
    mock_time.side_effect = [100.0, 100.0, 102.0, 102.0]

    gemini_client._enforce_call_spacing()
    gemini_client._enforce_call_spacing()

    mock_sleep.assert_called_once_with(gemini_client.MIN_SECONDS_BETWEEN_CALLS - 2.0)


@patch("gemini_client.get_client")
def test_call_agent_parses_response_and_validates(mock_get_client):
    gemini_client._last_call_timestamp = None
    mock_client = mock_get_client.return_value
    mock_client.models.generate_content.return_value = _fake_response('{"ok": true}', thoughts=10, output=5)

    with patch("gemini_client._enforce_call_spacing"):
        result = gemini_client.call_agent(
            system_prompt="sys", user_prompt="usr",
            schema=TEST_SCHEMA, schema_name="test_schema",
        )

    assert result == {"ok": True}
    # Confirm additionalProperties was actually stripped before sending -
    # this is what makes the Gemini integration work at all (see
    # _to_gemini_schema's docstring for the 400 error this avoids).
    sent_schema = mock_client.models.generate_content.call_args.kwargs["config"].response_schema
    assert "additionalProperties" not in sent_schema


@patch("gemini_client.get_client")
def test_call_agent_raises_clearly_when_response_has_no_text(mock_get_client):
    # Mirrors blocked-by-safety-filter or fully-truncated-before-any-output
    # cases - should fail with a clear message, not a confusing AttributeError.
    gemini_client._last_call_timestamp = None
    mock_client = mock_get_client.return_value
    blocked_response = type("R", (), {
        "text": None,
        "candidates": [type("Cand", (), {"finish_reason": "SAFETY"})()],
    })()
    mock_client.models.generate_content.return_value = blocked_response

    with patch("gemini_client._enforce_call_spacing"):
        try:
            gemini_client.call_agent(
                system_prompt="sys", user_prompt="usr",
                schema=TEST_SCHEMA, schema_name="test_schema",
            )
            assert False, "expected a ValueError"
        except ValueError as e:
            assert "test_schema" in str(e)
            assert "SAFETY" in str(e)


@patch("gemini_client.get_client")
def test_call_agent_retries_on_rate_limit_then_succeeds(mock_get_client):
    gemini_client._last_call_timestamp = None

    class FakeResourceExhausted(Exception):
        status_code = 429

    mock_client = mock_get_client.return_value
    mock_client.models.generate_content.side_effect = [
        FakeResourceExhausted("resource_exhausted"),
        _fake_response('{"ok": true}'),
    ]

    with patch("gemini_client.time.sleep"), patch("gemini_client._enforce_call_spacing"):
        result = gemini_client.call_agent(
            system_prompt="sys", user_prompt="usr",
            schema=TEST_SCHEMA, schema_name="test_schema",
        )

    assert result == {"ok": True}
    assert mock_client.models.generate_content.call_count == 2
