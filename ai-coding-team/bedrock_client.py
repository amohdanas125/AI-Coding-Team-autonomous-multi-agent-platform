"""Thin wrapper around AWS Bedrock's Converse API for strict-mode
structured tool-use output. Deliberately exposes the SAME call_agent(...)
interface as groq_client.py - every agent in agents/*.py imports call_agent
from whichever client module is currently in use, so switching providers
is a one-line import change per agent file (from groq_client import
call_agent -> from bedrock_client import call_agent), nothing else needs
to change. schemas.py needs no changes either - Bedrock's strict tool use
requires the same additionalProperties:false + all-fields-required
convention Groq's strict mode required, which every schema already follows.

IMPORTANT: this file could only be syntax-checked, not tested against the
live Bedrock API, in the sandbox that built this (no network access to
amazonaws.com from there - only pypi.org/npmjs.com/github.com and a
handful of others are reachable). Run scripts/smoke_test_bedrock.py
yourself, with real AWS credentials, before relying on this.

SETUP NEEDED BEFORE THIS WORKS, beyond an AWS account:
1. AWS credentials in .env: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
   AWS_DEFAULT_REGION (us-east-1 is a safe default - matches the "us."
   prefix on DEFAULT_MODEL below). Unlike Groq, this is IAM-based auth,
   not a single bearer key.
2. Model access: AWS Console -> Bedrock -> Model access -> request access
   to Anthropic's Claude models. This is a separate, explicit step from
   having valid credentials - a request with valid credentials still
   fails with an AccessDenied error if the model itself isn't enabled for
   your account yet.
3. This is NOT free the way Groq's free tier was - Bedrock bills per
   token. Check current pricing at aws.amazon.com/bedrock/pricing before
   running this against a real app-sized spec, and consider setting an
   AWS budget alert before your first real run.

MODEL CHOICE: defaults to Claude Sonnet 4.5 via its cross-region inference
profile ID, a deliberately conservative pick over the newer Claude
Sonnet 5. Sonnet 4.5 has been generally available on Bedrock since
September 2025 (Sonnet 5 only since June 2026), so it's had far longer to
shake out region-availability and on-demand-throughput rough edges -
newer Bedrock model IDs sometimes reject on-demand invocation entirely
and demand a cross-region inference profile ARN instead, which is more
setup than a first pass through this needs. Swap DEFAULT_MODEL below if
you want the newer model instead (likely "global.anthropic.claude-sonnet-5"
or "us.anthropic.claude-sonnet-5" - confirm the exact current ID in the
Bedrock console before switching, model IDs shift over time).
"""
import json
import os
import threading
import time

import boto3

from schemas import validate_payload

DEFAULT_MODEL = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# Same conservative default as groq_client.py's spacing. Bedrock's default
# quotas are typically far higher than Groq's free tier, but this is cheap
# insurance against a brand-new AWS account's initial limits - shrink or
# remove it once you've confirmed your account's real headroom.
MIN_SECONDS_BETWEEN_CALLS = 15

_client = None
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


def get_client():
    global _client
    if _client is None:
        if not os.environ.get("AWS_ACCESS_KEY_ID"):
            raise RuntimeError(
                "AWS_ACCESS_KEY_ID not set - copy .env.example to .env and fill in "
                "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION"
            )
        region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")
        _client = boto3.client("bedrock-runtime", region_name=region)
    return _client


def call_agent(system_prompt: str, user_prompt: str, schema: dict, schema_name: str,
                model: str = DEFAULT_MODEL, max_tokens: int = 4000,
                max_retries: int = 3) -> dict:
    """Same contract as groq_client.call_agent: get back a dict that's
    guaranteed to match `schema`, or an exception. Internally this means a
    single forced tool call with strict:true - Bedrock's mechanism for the
    same guarantee Groq's response_format json_schema strict:true gives -
    rather than a plain-text completion.

    Every call waits for MIN_SECONDS_BETWEEN_CALLS since the last one
    first. On a throttling response anyway, retries with backoff (20s,
    40s, ...) up to max_retries times."""
    _enforce_call_spacing()
    client = get_client()

    for attempt in range(max_retries):
        try:
            response = client.converse(
                modelId=model,
                system=[{"text": system_prompt}],
                messages=[{"role": "user", "content": [{"text": user_prompt}]}],
                inferenceConfig={"maxTokens": max_tokens},
                toolConfig={
                    "tools": [{
                        "toolSpec": {
                            "name": schema_name,
                            "description": f"Return data matching the {schema_name} schema.",
                            "strict": True,
                            "inputSchema": {"json": schema},
                        }
                    }],
                    "toolChoice": {"tool": {"name": schema_name}},
                },
            )
            break
        except Exception as e:
            error_code = getattr(e, "response", {}).get("Error", {}).get("Code", "")
            is_throttling = error_code in ("ThrottlingException", "TooManyRequestsException")
            if is_throttling and attempt < max_retries - 1:
                wait_seconds = 20 * (attempt + 1)
                print(f"  [throttled on '{schema_name}', waiting {wait_seconds}s "
                      f"before retry {attempt + 2}/{max_retries}]")
                time.sleep(wait_seconds)
                continue
            raise

    payload = None
    for block in response["output"]["message"]["content"]:
        if "toolUse" in block:
            payload = block["toolUse"]["input"]
            break

    if payload is None:
        raise ValueError(
            f"No tool-use block in Bedrock's response for '{schema_name}' - the model "
            f"replied with something other than the forced tool call. Full response: {response}"
        )

    validate_payload(payload, schema)
    return payload
