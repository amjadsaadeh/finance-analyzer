"""Approval state management for human-in-the-loop write operations.

When an agent calls a write tool (tags, category), the runner pauses and
produces interruptions.  We:
1. Serialise the RunState keyed by session_id (one pending state per session)
2. Format the interruptions into a human-readable preview
3. On approval/rejection, load the state and call approve/reject
"""

from __future__ import annotations

import time
from typing import Any

from agents import Agent, RunState
from agents.items import ToolApprovalItem

# ---------------------------------------------------------------------------
# In-memory state store (keyed by session_id)
# ---------------------------------------------------------------------------

STATE_TTL_SECONDS = 10 * 60  # 10 minutes

_pending_states: dict[str, dict[str, Any]] = {}


def store_state(state: RunState, session_id: str) -> str:
    """Serialise and store a RunState keyed by session_id.

    Returns the state_id (which is the session_id for simplicity —
    only one pending approval per session at a time).
    """
    state_id = session_id
    # Serialise using the SDK's built-in serialisation
    state_json = state.to_json()
    _pending_states[state_id] = {
        "state_json": state_json,
        "stored_at": time.monotonic(),
        "starting_agent": state.starting_agent,
    }
    return state_id


def load_state(state_id: str, starting_agent: Agent) -> RunState | None:
    """Load and remove a stored RunState.

    Returns None if the state has expired or doesn't exist.
    """
    entry = _pending_states.pop(state_id, None)
    if entry is None:
        return None

    age = time.monotonic() - entry["stored_at"]
    if age > STATE_TTL_SECONDS:
        return None  # expired

    state = RunState.from_json(
        initial_agent=starting_agent,
        state_json=entry["state_json"],
    )
    return state


def format_approval_preview(interruptions: list[ToolApprovalItem]) -> dict[str, Any]:
    """Format interruptions into a human-readable preview dict.

    Each interrupted tool call produces:
    - tool_name: the tool being called
    - arguments: the arguments that will be applied
    - summary: a natural-language description of what will change
    """
    previews = []
    for interruption in interruptions:
        tool_name = interruption.tool_name or interruption.name or "unknown"
        try:
            arguments = (
                interruption.arguments
                if isinstance(interruption.arguments, dict)
                else {}
            )
        except (AttributeError, TypeError):
            arguments = {}

        # Build a natural-language summary
        summary = _summarise_tool_call(tool_name, arguments)

        previews.append(
            {
                "tool_name": tool_name,
                "arguments": arguments,
                "summary": summary,
            }
        )

    return {"previews": previews, "count": len(previews)}


def _summarise_tool_call(tool_name: str, arguments: dict) -> str:
    """Produce a one-line human summary of a pending write operation."""
    if tool_name == "update_transaction_category":
        tx_id = arguments.get("transaction_id", "?")
        category = arguments.get("category_name", "?")
        return f"Update category of transaction '{tx_id}' to '{category}'"
    if tool_name == "update_transaction_tags":
        tx_id = arguments.get("transaction_id", "?")
        tags = arguments.get("tags", [])
        tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
        return f"Update tags of transaction '{tx_id}' to [{tags_str}]"
    return f"Call {tool_name} with {arguments}"