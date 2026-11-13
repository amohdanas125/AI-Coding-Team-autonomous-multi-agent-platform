"""Thin wrapper around the Google Gemini API for structured JSON output.

Mirrors groq_client.py's call_agent(...) signature and return shape
exactly, so any agents/*.py module can switch providers by changing only
its import line, e.g. in agents/frontend_developer.py:

    # from groq_client import call_agent
    from gemini_client import call_agent

Nothing else in an agent file needs to change - prompts, schemas, and
generate_frontend()/generate_backend()'s own signatures stay identical.

FREE-TIER CONSTRAINT - READ BEFORE TUNING: unlike Groq's free tier (a hard
tokens-per-single-request ceiling that no retry can fix - see
groq_client.py's docstring), Gemini's free tier is generally gated on
REQUESTS PER MINUTE with a much larger per-request token budget. That
means the aggressive per-page/per-entity prompt-splitting you did for
Groq is less likely to be strictly necessary here, though it's still
good practice to keep (smaller prompts = fewer tokens = cheaper on paid
tiers later, and won't hurt on free tier either).

The exact RPM/RPD numbers change over time and differ per model (Flash
vs Flash-Lite vs Pro) - don't trust a hardcoded number here or anywhere
else. Check the live numbers yourself before tuning
MIN_SECONDS_BETWEEN_CALLS below:
    https://ai.google.dev/gemini-api/docs/rate-limits

MODEL NAME NOTE: Google retires model names with little warning - a call
that worked last month can start returning "404 NOT_FOUND ... no longer
available to new users" with no code change on your end (this file's
original default, "gemini-2.5-flash", hit exactly this in mid-2026). A
404 mentioning a model name means Google moved the model, not a bug
here - check the current list and update the `model` default below:
    https://ai.google.dev/gemini-api/docs/models
As of writing, "gemini-3.5-flash" (this file's current default) is the
GA flagship; "gemini-3.1-flash-lite" is a cheaper/higher-throughput
alternative if you want to conserve free-tier quota over output quality.

SCHEMA COMPATIBILITY NOTE: schemas.py's schemas use
"additionalProperties": False and every property in "required" (written
for Groq/OpenAI-style strict mode). Gemini's structured-output support
has expanded to cover more of standard JSON Schema, but historically its
schema format was a stricter OpenAPI 3.0 subset that didn't accept every
JSON Schema keyword. Run the self-test at the bottom of this file
(`python gemini_client.py`) against your actual schemas.py schemas before
wiring this into an agent - if Gemini rejects a keyword, you'll see a
clear error there instead of mid-run in a real generation.
"""
import json
import os
import threading
import time
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types

from schemas import validate_payload

_client = None

# Minimum seconds between any two calls to Gemini, process-wide - same
# defensive pattern as groq_client.py's MIN_SECONDS_BETWEEN_CALLS. This is
# a conservative starting guess, NOT a verified number - tune it against
# whatever ai.google.dev/gemini-api/docs/rate-limits shows for your chosen
# model right now.
MIN_SECONDS_BETWEEN_CALLS = 5

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


def get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set - copy .env.example to .env and fill it in")
        _client = genai.Client(api_key=api_key)
    return _client


def _to_gemini_schema(schema):
    """Strip keys Gemini's response_schema doesn't accept, recursively.

    Confirmed live: Gemini rejects "additionalProperties" outright (400
    INVALID_ARGUMENT, 'Unknown name "additional_properties"'), even though
    schemas.py sets it on every object per its strict-mode docstring. That
    key is meaningless to Gemini's generation anyway - it's OpenAI/Groq
    strict-mode's way of saying "no extra keys", but Gemini has no
    equivalent knob, and this app's real defense against extra/malformed
    keys is validate_payload() running locally regardless of provider (see
    that function's docstring). So: strip it here for what gets SENT to
    Gemini, but keep validating the ORIGINAL untouched schema in
    call_agent below - this function must never be used as a substitute
    for validate_payload.

    Deep-copies rather than mutating, since callers pass in the same
    schema objects (e.g. FRONTEND_PAGE_OUTPUT_SCHEMA) that other code
    also uses for local validation - mutating them in place would corrupt
    every other call site in the process.
    """
    if isinstance(schema, dict):
        return {
            key: _to_gemini_schema(value)
            for key, value in schema.items()
            if key != "additionalProperties"
        }
    if isinstance(schema, list):
        return [_to_gemini_schema(item) for item in schema]
    return schema


def call_agent(system_prompt: str, user_prompt: str, schema: dict, schema_name: str,
                model: str = "gemini-3.8-flash", max_tokens: int = 8000,
                max_retries: int = 2) -> dict:
    """Call Gemini with a JSON response schema, parse the JSON, and
    validate it locally against `schema` before returning.

    Same contract as groq_client.call_agent: same argument names/order,
    same return shape (a parsed + locally-validated dict). Local
    validation happens regardless of Gemini's own schema adherence - same
    reasoning as groq_client.py: don't trust any provider's "guaranteed
    schema" claim blindly, treat a validation failure as an agent failure
    to retry, same as a QA failure.

    On a 429 (rate limit / resource exhausted) response, retries with
    backoff (20s, 40s, ...) up to max_retries times, mirroring
    groq_client.py's behavior. Unlike Groq, a 429 here is much more
    likely to be a genuinely transient RPM collision that backoff can
    fix, rather than a single request that's fundamentally too large -
    but if you see the SAME call fail on every retry, that's a sign this
    assumption doesn't hold for your prompt size and you should shrink
    the request instead (same lesson Groq taught you)."""
    _enforce_call_spacing()
    client = get_client()
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=_to_gemini_schema(schema),
                    max_output_tokens=max_tokens,
                    # Gemini 3.5's default thinking_level ("medium") burns
                    # reasoning tokens out of the SAME max_output_tokens
                    # budget as the actual response, before any content is
                    # produced - confirmed live: a 2500-token budget with
                    # default thinking produced truncated JSON because
                    # thinking ate into it first. "low" leaves more budget
                    # for real output; this is a structured code-gen task,
                    # not one that benefits much from deep reasoning anyway.
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                ),
            )
            break
        except Exception as e:
            status_code = getattr(e, "status_code", None) or getattr(e, "code", None)
            is_rate_limit = (
                status_code == 429
                or "429" in str(e)
                or "resource_exhausted" in str(e).lower()
            )
            is_transient = (
                is_rate_limit
                or status_code in (500, 502, 503, 504)
                or "503" in str(e)
                or "unavailable" in str(e).lower()
                or "high demand" in str(e).lower()
            )
            if is_transient and attempt < max_retries - 1:
                wait_seconds = 5 * (attempt + 1)
                reason = "rate limited" if is_rate_limit else "temporary server overload/503"
                print(f"  [{reason} on '{schema_name}', waiting {wait_seconds}s "
                      f"before retry {attempt + 2}/{max_retries}]")
                time.sleep(wait_seconds)
                continue
            if is_transient and os.environ.get("GROQ_API_KEY"):
                print(f"  [Gemini server overload/503 on '{schema_name}' after retries - falling back to Groq]")
                import groq_client
                return groq_client.call_agent(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    schema=schema,
                    schema_name=schema_name,
                )
            raise

    raw = response.text
    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        thoughts = getattr(usage, "thoughts_token_count", None) or 0
        output = getattr(usage, "candidates_token_count", None) or 0
        print(f"  [{schema_name}] tokens - thinking: {thoughts}, output: {output}, "
              f"budget: {max_tokens}")

    if raw is None:
        finish_reason = None
        if response.candidates:
            finish_reason = response.candidates[0].finish_reason
        raise ValueError(
            f"Response for '{schema_name}' had no text content - likely blocked by a "
            f"safety filter or cut off by max_output_tokens={max_tokens}. "
            f"finish_reason: {finish_reason}"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Response for '{schema_name}' wasn't valid JSON - most likely truncated "
            f"by max_output_tokens={max_tokens} (see token breakdown printed above - "
            f"if thinking+output is close to or over budget, that confirms it). If this "
            f"is a code-generating agent, try raising max_tokens. "
            f"Response started with: {raw[:200]!r}"
        ) from e
    validate_payload(payload, schema)
    return payload


if __name__ == "__main__":
    # Self-test: confirm Gemini accepts your actual schemas.py schemas
    # as-is (additionalProperties: False, every key in required, etc.)
    # before you wire this into a real agent. Run with:
    #   python gemini_client.py
    # Requires GEMINI_API_KEY set in your environment (or .env, if you
    # add python-dotenv's load_dotenv() call here like groq_client.py's
    # callers do).
    from schemas import FRONTEND_PAGE_OUTPUT_SCHEMA

    print("Testing gemini_client.call_agent against FRONTEND_PAGE_OUTPUT_SCHEMA...")
    result = call_agent(
        system_prompt="You are a test agent. Return a single trivial file.",
        user_prompt='Return one file: path "test.txt", content "hello from gemini".',
        schema=FRONTEND_PAGE_OUTPUT_SCHEMA,
        schema_name="frontend_page_output",
        max_tokens=500,
    )
    print("OK - schema accepted and response validated:")
    print(json.dumps(result, indent=2))
