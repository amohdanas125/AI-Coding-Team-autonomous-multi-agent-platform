"""Tests for bedrock_client.py's own logic - call spacing, retry-on-throttle,
and Converse API response parsing (the toolUse extraction, which is new
and Bedrock-specific - groq_client.py's tests don't cover this since
Groq's response shape is different). Doesn't touch the network: patches
time.sleep/time.time/boto3 so these run instantly and without credentials.
"""
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bedrock_client

TEST_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def _fake_converse_response(tool_input=None, include_tool_use=True):
    content = []
    if include_tool_use:
        content.append({"toolUse": {"name": "test_schema", "input": tool_input or {"ok": True}}})
    else:
        content.append({"text": "I'd rather just respond in plain text."})
    return {"output": {"message": {"content": content}}}


@patch("bedrock_client.time.sleep")
@patch("bedrock_client.time.time")
def test_enforce_call_spacing_waits_when_calls_are_close_together(mock_time, mock_sleep):
    bedrock_client._last_call_timestamp = None
    mock_time.side_effect = [100.0, 100.0, 105.0, 105.0]

    bedrock_client._enforce_call_spacing()
    bedrock_client._enforce_call_spacing()

    mock_sleep.assert_called_once_with(bedrock_client.MIN_SECONDS_BETWEEN_CALLS - 5.0)


@patch("bedrock_client.get_client")
def test_call_agent_extracts_tool_use_input_correctly(mock_get_client):
    bedrock_client._last_call_timestamp = None
    mock_client = mock_get_client.return_value
    mock_client.converse.return_value = _fake_converse_response(tool_input={"ok": True})

    with patch("bedrock_client._enforce_call_spacing"):
        result = bedrock_client.call_agent(
            system_prompt="sys", user_prompt="usr",
            schema=TEST_SCHEMA, schema_name="test_schema",
        )

    assert result == {"ok": True}
    # Confirm strict:true and a forced tool choice were actually sent -
    # these two are what make the schema guarantee real, not decorative.
    call_kwargs = mock_client.converse.call_args.kwargs
    tool_spec = call_kwargs["toolConfig"]["tools"][0]["toolSpec"]
    assert tool_spec["strict"] is True
    assert call_kwargs["toolConfig"]["toolChoice"] == {"tool": {"name": "test_schema"}}


@patch("bedrock_client.get_client")
def test_call_agent_raises_clearly_when_model_ignores_forced_tool_choice(mock_get_client):
    # Mirrors the real-world Groq case we already hit once (strict mode
    # silently ignored) - if Bedrock ever does the same, this should fail
    # loudly with a useful message, not a confusing KeyError.
    bedrock_client._last_call_timestamp = None
    mock_client = mock_get_client.return_value
    mock_client.converse.return_value = _fake_converse_response(include_tool_use=False)

    with patch("bedrock_client._enforce_call_spacing"):
        try:
            bedrock_client.call_agent(
                system_prompt="sys", user_prompt="usr",
                schema=TEST_SCHEMA, schema_name="test_schema",
            )
            assert False, "expected a ValueError"
        except ValueError as e:
            assert "test_schema" in str(e)


@patch("bedrock_client.get_client")
def test_call_agent_retries_on_throttling_then_succeeds(mock_get_client):
    bedrock_client._last_call_timestamp = None

    class FakeThrottlingError(Exception):
        response = {"Error": {"Code": "ThrottlingException"}}

    mock_client = mock_get_client.return_value
    mock_client.converse.side_effect = [
        FakeThrottlingError("slow down"),
        _fake_converse_response(tool_input={"ok": True}),
    ]

    with patch("bedrock_client.time.sleep"), patch("bedrock_client._enforce_call_spacing"):
        result = bedrock_client.call_agent(
            system_prompt="sys", user_prompt="usr",
            schema=TEST_SCHEMA, schema_name="test_schema",
        )

    assert result == {"ok": True}
    assert mock_client.converse.call_count == 2
