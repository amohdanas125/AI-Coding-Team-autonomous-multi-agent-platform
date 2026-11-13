"""Run this yourself, locally, after setting AWS_ACCESS_KEY_ID,
AWS_SECRET_ACCESS_KEY, and AWS_DEFAULT_REGION in .env, AND after enabling
model access for Claude Sonnet 4.5 in the Bedrock console (AWS Console ->
Bedrock -> Model access). Neither of those two things could be verified
from the sandbox that built this (no network access to amazonaws.com
there, and model access has to be granted through the console regardless).

    python scripts/smoke_test_bedrock.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from bedrock_client import call_agent

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
    print("If this printed a dict with 'title' and 'year' and no traceback, Bedrock strict")
    print("tool use is working. If you get an AccessDeniedException, that almost always")
    print("means credentials are fine but model access hasn't been enabled yet - go to")
    print("AWS Console -> Bedrock -> Model access and request access to Claude models.")
