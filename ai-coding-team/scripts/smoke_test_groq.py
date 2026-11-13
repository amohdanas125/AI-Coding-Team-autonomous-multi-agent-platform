"""Run this yourself, locally, after setting GROQ_API_KEY in .env.
It could NOT be run from the sandbox that built this scaffold (no network
access to api.groq.com there) - this confirms strict-mode Structured
Outputs actually works end-to-end against the live API before you build
Phase 1 on top of it.

    python scripts/smoke_test_groq.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from groq_client import call_agent

TEST_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "year": {"type": "integer"},
    },
    "required": ["title", "year"],
    "additionalProperties": False,
}

if __name__ == "__main__":
    result = call_agent(
        system_prompt="You return structured data about famous papers.",
        user_prompt="Give me the title and publication year of the 'Attention Is All You Need' paper.",
        schema=TEST_SCHEMA,
        schema_name="paper_info",
    )
    print("Got back:", result)
    print("If this printed a dict with 'title' and 'year' and no traceback, strict mode is working.")
