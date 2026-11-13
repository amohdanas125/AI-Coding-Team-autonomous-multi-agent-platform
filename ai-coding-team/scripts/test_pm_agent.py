"""Run this yourself, locally, with a real GROQ_API_KEY set in .env.

This is the "run it against all 5 sample prompts and eyeball the specs
before touching any other agent" step the master prompt asked for -
it could NOT be run from the sandbox that built Phase 1 (no network access
to api.groq.com there), so it's prepared and ready for you to execute.

    python scripts/test_pm_agent.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from agents.project_manager import generate_spec
from schemas import PM_SPEC_SCHEMA, validate_payload

SAMPLE_PROMPTS = [
    "Build a to-do list app with user accounts",
    "Build a food delivery website",
    "Build a library book borrowing system",
    "Build a gym membership tracker with class bookings",
    "Build a simple blog platform with posts and comments",
]

if __name__ == "__main__":
    for prompt in SAMPLE_PROMPTS:
        print(f"\n{'=' * 70}\nPROMPT: {prompt}\n{'=' * 70}")
        spec = generate_spec(prompt)
        # Raises if strict mode was silently ignored (see schemas.py docstring) -
        # if this line throws, that's Groq returning a non-conforming response,
        # not a bug in this script.
        validate_payload(spec, PM_SPEC_SCHEMA)
        print(json.dumps(spec, indent=2))
        print(f"-> {len(spec['entities'])} entities, {len(spec['endpoints'])} endpoints, "
              f"{len(spec['pages'])} pages, auth_required={spec['auth_required']}")

    print("\nAll 5 prompts produced schema-valid specs. Eyeball them above -\n"
          "check entities/fields make sense, no entity has an 'id' field,\n"
          "'reference' fields point to real entity names, and endpoint/page\n"
          "counts are sensible - before starting Phase 2 (Backend Developer).")
