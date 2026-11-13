"""Shared state that flows through the LangGraph graph for one build task."""
from typing import TypedDict, Optional, List


class BuildState(TypedDict):
    task_id: str
    user_prompt: str

    spec: Optional[dict]              # PM_SPEC_SCHEMA-shaped, set by project_manager
    backend_output: Optional[dict]    # BACKEND_OUTPUT_SCHEMA-shaped, set by backend_developer
    frontend_output: Optional[dict]   # FRONTEND_OUTPUT_SCHEMA-shaped, set by frontend_developer
    qa_report: Optional[dict]         # QA_REPORT_SCHEMA-shaped, set by qa_engineer
    docs_output: Optional[dict]       # DOCS_OUTPUT_SCHEMA-shaped, set by documentation_writer

    qa_attempt: int                   # incremented every time qa_engineer runs
    needs_human_review: bool          # True if qa_attempt hit the cap while still failing
    agent_log: List[dict]             # envelope dicts appended by every node - Phase 7 evaluation data


def initial_state(task_id: str, user_prompt: str) -> BuildState:
    return {
        "task_id": task_id,
        "user_prompt": user_prompt,
        "spec": None,
        "backend_output": None,
        "frontend_output": None,
        "qa_report": None,
        "docs_output": None,
        "qa_attempt": 0,
        "needs_human_review": False,
        "agent_log": [],
    }
