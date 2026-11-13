"""Thin wrapper around the OpenAI API for strict Structured Outputs.
Mirrors groq_client.py's and gemini_client.py's call_agent(...) signature
and return shape exactly, so any agents/*.py module can switch providers
by changing only its import line:

    from openai_client import call_agent

OpenAI natively supports strict structured outputs (strict: True) on
models like gpt-4o, gpt-4o-mini, etc.
"""
import json
import os
import threading
import time
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
from schemas import validate_payload

_client = None

# Defensive 1-second process-wide spacing between OpenAI calls
MIN_SECONDS_BETWEEN_CALLS = 1

_last_call_timestamp = None
_rate_limit_lock = threading.Lock()


def _enforce_call_spacing():
    global _last_call_timestamp
    with _rate_limit_lock:
        now = time.time()
        if _last_call_timestamp is not None:
            elapsed = now - _last_call_timestamp
            if elapsed < MIN_SECONDS_BETWEEN_CALLS:
                time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
        _last_call_timestamp = time.time()


def get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set - copy .env.example to .env and fill it in")
        _client = OpenAI(api_key=api_key)
    return _client


def call_agent(
    system_prompt: str,
    user_prompt: str,
    schema: dict,
    schema_name: str,
    model: str | None = None,
    max_tokens: int = 4096,
    max_retries: int = 3,
) -> dict:
    """Call OpenAI with strict Structured Outputs, parse the JSON, and
    validate it locally against `schema` before returning."""
    _enforce_call_spacing()
    client = get_client()

    chosen_model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")

    response = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=chosen_model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema_name,
                        "strict": True,
                        "schema": schema,
                    },
                },
            )
            break
        except Exception as e:
            status_code = getattr(e, "status_code", None)
            is_rate_limit = status_code in (429, 413) or "rate_limit" in str(e).lower()
            if is_rate_limit and attempt < max_retries - 1:
                wait_seconds = 5 * (attempt + 1)
                print(f"  [OpenAI rate limited on '{schema_name}', waiting {wait_seconds}s before retry {attempt + 2}/{max_retries}]")
                time.sleep(wait_seconds)
                continue
            raise

    raw = response.choices[0].message.content
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Response for '{schema_name}' wasn't valid JSON - truncated by max_tokens={max_tokens}?\n"
            f"Response: {raw[:300]!r}"
        ) from e

    validate_payload(payload, schema)
    return payload


if __name__ == "__main__":
    from schemas import FRONTEND_PAGE_OUTPUT_SCHEMA
    print("Testing openai_client.call_agent against FRONTEND_PAGE_OUTPUT_SCHEMA...")
    result = call_agent(
        system_prompt="You are a test agent. Return a single trivial file.",
        user_prompt="Return a file at path 'test.txt' with content 'hello from openai'.",
        schema=FRONTEND_PAGE_OUTPUT_SCHEMA,
        schema_name="frontend_page_output",
        max_tokens=500,
    )
    print("OK - schema accepted and response validated:")
    print(json.dumps(result, indent=2))
