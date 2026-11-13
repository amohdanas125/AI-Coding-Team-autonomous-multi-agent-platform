"""
LangGraph topology for the AI Coding Team pipeline.

Phase 4 status: project_manager, backend_developer, frontend_developer,
and qa_engineer are all REAL agents now. qa_engineer is a different kind
of real, though - it doesn't just generate code, it actually executes
the generated backend's tests (npm install, an in-memory MongoDB, Jest)
in a sandboxed temp directory, so this node is genuinely slower than the
others. documentation_writer is still a STUB returning fake-but-schema-
shaped data.

Graph shape:

    START -> project_manager -> backend_developer -(first run)-> frontend_developer -> qa_engineer
                                 backend_developer -(retry)-------------------------------^
             qa_engineer --(fail, attempt < 3)--> backend_developer            (loop back)
             qa_engineer --(pass, or attempt >= 3)--> documentation_writer -> END

Design call I made that isn't specified in the master prompt: on a QA-
triggered retry, backend_developer routes straight back to qa_engineer,
NOT through frontend_developer again. Frontend didn't cause the failure
and doesn't need to be regenerated just because a backend test failed -
only compile it once. This is implemented as a conditional edge out of
backend_developer (route_after_backend) that checks whether
frontend_output already exists yet, rather than the fixed linear edge
you'd get from following the phase list literally.
"""
import time
from langgraph.graph import StateGraph, START, END

from orchestrator.state import BuildState
from schemas import make_envelope
from agents.project_manager import generate_spec
from agents.backend_developer import generate_backend
from agents.frontend_developer import generate_frontend
from agents.qa_engineer import generate_qa_report
from agents.documentation_writer import generate_docs

MAX_QA_ATTEMPTS = 3


def _log(state: BuildState, from_agent: str, to_agent: str, status: str, payload: dict) -> dict:
    entry = make_envelope(from_agent, to_agent, state["task_id"], status, payload)
    entry["timestamp"] = time.time()
    return entry


# --- Node functions ----------------------------------------------------
# project_manager_node, backend_developer_node, frontend_developer_node, and
# qa_engineer_node are all REAL (see agents/*.py). documentation_writer_node
# is the last remaining STUB, returning fake-but-schema-shaped data until
# Phase 5.

def project_manager_node(state: BuildState) -> dict:
    spec = generate_spec(state["user_prompt"])
    log = _log(state, "project_manager", "backend_developer", "done", spec)
    return {"spec": spec, "agent_log": state["agent_log"] + [log]}


def backend_developer_node(state: BuildState) -> dict:
    is_retry = state["qa_report"] is not None
    output = generate_backend(
        state["spec"],
        qa_report=state.get("qa_report"),
        previous_output=state.get("backend_output"),
    )
    next_agent = "qa_engineer" if is_retry else "frontend_developer"
    log = _log(state, "backend_developer", next_agent, "done", output)
    return {"backend_output": output, "agent_log": state["agent_log"] + [log]}


def frontend_developer_node(state: BuildState) -> dict:
    output = generate_frontend(state["spec"], state["backend_output"]["api_contract"])
    log = _log(state, "frontend_developer", "qa_engineer", "done", output)
    return {"frontend_output": output, "agent_log": state["agent_log"] + [log]}


def qa_engineer_node(state: BuildState) -> dict:
    # REAL as of Phase 4 - genuinely runs the generated backend's tests
    # (npm install, an in-memory MongoDB, Jest) rather than returning
    # canned data. This is slower than every other node - it's doing real
    # subprocess work, not just an LLM call.
    attempt = state["qa_attempt"] + 1
    report = generate_qa_report(state["spec"], state["backend_output"])
    passed = report["all_tests_passed"]
    next_agent = "documentation_writer" if (passed or attempt >= MAX_QA_ATTEMPTS) else "backend_developer"
    log = _log(state, "qa_engineer", next_agent, "done", report)
    return {"qa_report": report, "qa_attempt": attempt, "agent_log": state["agent_log"] + [log]}


def documentation_writer_node(state: BuildState) -> dict:
    needs_review = not state["qa_report"]["all_tests_passed"]
    output = generate_docs(
        state["spec"],
        state["backend_output"],
        frontend_output=state.get("frontend_output"),
        qa_report=state.get("qa_report"),
        needs_human_review=needs_review,
    )
    log = _log(state, "documentation_writer", "orchestrator", "done", output)
    return {
        "docs_output": output,
        "needs_human_review": needs_review,
        "agent_log": state["agent_log"] + [log],
    }


# --- Routing ------------------------------------------------------------

def route_after_backend(state: BuildState) -> str:
    if state["frontend_output"] is None:
        return "frontend_developer"
    return "qa_engineer"


def route_after_qa(state: BuildState) -> str:
    if state["qa_report"]["all_tests_passed"]:
        return "documentation_writer"
    if state["qa_attempt"] >= MAX_QA_ATTEMPTS:
        return "documentation_writer"  # give up, needs_human_review gets flagged in docs node
    return "backend_developer"


# --- Graph assembly -------------------------------------------------------

def build_graph():
    graph = StateGraph(BuildState)

    graph.add_node("project_manager", project_manager_node)
    graph.add_node("backend_developer", backend_developer_node)
    graph.add_node("frontend_developer", frontend_developer_node)
    graph.add_node("qa_engineer", qa_engineer_node)
    graph.add_node("documentation_writer", documentation_writer_node)

    graph.add_edge(START, "project_manager")
    graph.add_edge("project_manager", "backend_developer")
    graph.add_conditional_edges("backend_developer", route_after_backend, {
        "frontend_developer": "frontend_developer",
        "qa_engineer": "qa_engineer",
    })
    graph.add_edge("frontend_developer", "qa_engineer")
    graph.add_conditional_edges("qa_engineer", route_after_qa, {
        "backend_developer": "backend_developer",
        "documentation_writer": "documentation_writer",
    })
    graph.add_edge("documentation_writer", END)

    return graph.compile()
