"""Thin wrapper around the Groq API for strict-mode Structured Outputs.
Used for real by every agent in agents/*.py - all live-verified except
Frontend Developer's actual generated-code quality.

IMPORTANT: this file could only be syntax-checked, not tested against the
live Groq API, in the sandbox that built this scaffold (no network access
to api.groq.com from there). Every agent that uses it needs its own live
verification script under scripts/, run by hand with a real GROQ_API_KEY.

FREE-TIER CONSTRAINT (discovered live, not anticipated): Groq's free tier
enforces a tokens-per-minute (TPM) limit - 8000 in the org that hit this,
on BOTH Backend Developer's and Frontend Developer's original single-call
designs (10760 and 11301 tokens requested respectively). This is a genuine
cap on (input tokens + max_tokens) for a SINGLE request; a request that
needs more than the limit will fail every time, no matter how long you
wait, since waiting only helps when usage is spread across several
smaller requests. Keep individual calls comfortably under this - see
agents/backend_developer.py and agents/frontend_developer.py for why they
each make several small calls instead of one big one.

Rate-limit spacing (MIN_SECONDS_BETWEEN_CALLS below) is enforced HERE,
centrally, rather than left to each agent to remember - the TPM budget is
per-account, shared across every agent's calls, not per-agent.
"""
import json
import os
import re
import threading
import time
from dotenv import load_dotenv

load_dotenv()

from groq import Groq

from schemas import validate_payload

_client = None

# Minimum seconds between any two calls to Groq, process-wide. A heuristic
# to reduce how often the reactive retry-with-backoff below even needs to
# fire - not empirically tuned against the live API (couldn't be, from the
# sandbox that built this), and safe to shrink or remove on a paid tier
# with a higher TPM limit.
MIN_SECONDS_BETWEEN_CALLS = 15

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


def get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY not set - copy .env.example to .env and fill it in")
        _client = Groq(api_key=api_key)
    return _client


def call_agent(system_prompt: str, user_prompt: str, schema: dict, schema_name: str,
                model: str = "openai/gpt-oss-120b", max_tokens: int = 6000,
                max_retries: int = 3) -> dict:
    """Call Groq with strict Structured Outputs, parse the JSON, and
    validate it locally against `schema` before returning. See schemas.py's
    module docstring for why local validation matters even with strict:true.

    max_tokens defaults to a size that's comfortable for a PM-sized spec.
    Code-generating agents should pass a larger value explicitly - a
    response cut off by max_tokens comes back as invalid JSON, not a clear
    "too long" error, so it's worth getting this right rather than
    debugging a confusing JSONDecodeError. But keep (input + max_tokens)
    under your account's TPM limit - see module docstring; retrying
    doesn't help if a single request is bigger than the whole limit -
    only a smaller request does.

    Every call waits for MIN_SECONDS_BETWEEN_CALLS since the last one
    first (see _enforce_call_spacing). On a 429/413 rate-limit response
    anyway, retries with backoff (20s, 40s, ...) up to max_retries times -
    this helps for transient overlap between calls but can't fix a single
    request that's simply too large on its own; that raises immediately."""
    _enforce_call_spacing()
    client = get_client()
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
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
            # Separate from rate limiting: Groq's own server-side schema
            # validator can reject a response as malformed JSON
            # (code: json_validate_failed) - seen live on a schema made
            # more deeply nested by adding seed_records, where the model
            # corrupted its own string escaping mid-generation. This is
            # usually sampling noise, not a hard limit like the TPM cap -
            # a retry with a fresh sample often succeeds where the first
            # attempt garbled its escaping. Distinct code path from
            # is_rate_limit so it's easy to tell from logs which kind of
            # failure actually happened.
            is_malformed_json = (
                status_code == 400 and "json_validate_failed" in str(e).lower()
            )
            if is_malformed_json:
                err_dict = getattr(e, "body", None)
                if isinstance(err_dict, dict) and "error" in err_dict:
                    failed_gen = err_dict["error"].get("failed_generation")
                    if failed_gen:
                        candidates = [
                            failed_gen,
                            re.sub(r"\\+'", "'", failed_gen),
                            re.sub(r"\\'", "'", failed_gen),
                            re.sub(r'\\(?![/"\\bfnrtu])', r'\\\\', re.sub(r"\\+'", "'", failed_gen)),
                        ]
                        for cand in candidates:
                            try:
                                payload = json.loads(cand)
                                validate_payload(payload, schema)
                                print(f"  [Rescued valid JSON from Groq's failed_generation on '{schema_name}']")
                                return payload
                            except Exception:
                                pass

            if (is_rate_limit or is_malformed_json) and attempt < max_retries - 1:
                wait_seconds = 20 * (attempt + 1) if is_rate_limit else 3
                reason = "rate limited" if is_rate_limit else "malformed JSON from model"
                print(f"  [{reason} on '{schema_name}', waiting {wait_seconds}s "
                      f"before retry {attempt + 2}/{max_retries}]")
                time.sleep(wait_seconds)
                continue
            raise

    raw = response.choices[0].message.content
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Response for '{schema_name}' wasn't valid JSON - most likely truncated "
            f"by max_tokens={max_tokens}. If this is a code-generating agent, try raising "
            f"max_tokens. Response started with: {raw[:200]!r}"
        ) from e
    validate_payload(payload, schema)
    return payload
