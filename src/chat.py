"""Chat endpoints: SSE streaming and approval flow.

Endpoints:
- GET  /chat/stream  — Stream agent responses via Server-Sent Events
- POST /chat/approve — Confirm or reject a pending write operation

SSE event types:
- text           — Agent text delta
- tool_call      — Agent invoked a tool
- approval_needed — Agent paused for user confirmation (write tool)
- done           — Response complete (no approval needed)
- error          — Something went wrong (natural language message)
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agents import Agent, Runner
from fastapi import APIRouter, Query, Request
from sse_starlette import EventSourceResponse

from src.agent import finance_agent
from src.approval import format_approval_preview, load_state, store_state
from src.models import ApproveRequest, ChatStreamRequest
from src.sessions import SessionStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_store(request: Request) -> SessionStore:
    """Retrieve the SessionStore from app state."""
    return request.app.state.session_store


# ---------------------------------------------------------------------------
# GET /chat/stream — SSE streaming
# ---------------------------------------------------------------------------


@router.get("/stream")
async def chat_stream(
    request: Request,
    message: str = Query(..., description="User message to send"),
    session_id: str = Query(..., description="Session ID for context"),
):
    """Stream agent responses via Server-Sent Events.

    Query parameters:
    - message: the user's question or instruction
    - session_id: persistent session identifier
    """
    store = _get_store(request)

    try:
        _, session = store.get_or_create_session(session_id)
    except (ValueError, EnvironmentError) as exc:
        # FireflyClient requires FIREFLY_BASE_URL and FIREFLY_API_TOKEN
        error_msg = f"Server configuration error: {exc}. Please check your environment settings."
        error_data = json.dumps({"message": error_msg})

        async def _error_gen():
            yield {"event": "error", "data": error_data}

        return EventSourceResponse(_error_gen())

    async def event_generator():
        try:
            # Append user message to session history
            session["messages"].append({"role": "user", "content": message})

            # Run agent with streaming
            result = Runner.run_streamed(
                finance_agent,
                session["messages"],
                context=session["client"],
            )

            assistant_text = ""

# Track which call_ids we've already emitted a tool_call event for,
            # so we don't send duplicates from both raw and run_item events.
            _emitted_tool_calls: set[str] = set()

            async for event in result.stream_events():
                # ---- Raw response events (text deltas, function calls) ----
                if event.type == "raw_response_event":
                    raw = event.data

                    # Text delta — stream to client
                    if hasattr(raw, "type") and raw.type == "response.output_text.delta":
                        delta = getattr(raw, "delta", "")
                        if delta:
                            assistant_text += delta
                            yield {
                                "event": "text",
                                "data": json.dumps({"content": delta}),
                            }

                    # Function call completed — emit tool_call event with name
                    elif (
                        hasattr(raw, "type")
                        and raw.type == "response.function_call_arguments.done"
                    ):
                        fn_name = getattr(raw, "name", None) or "unknown"
                        fn_args = getattr(raw, "arguments", "{}")
                        call_id = getattr(raw, "call_id", None) or getattr(raw, "item_id", None)
                        if call_id:
                            _emitted_tool_calls.add(call_id)
                        try:
                            args_dict = (
                                json.loads(fn_args)
                                if isinstance(fn_args, str)
                                else {}
                            )
                        except (json.JSONDecodeError, TypeError):
                            args_dict = {}
                        yield {
                            "event": "tool_call",
                            "data": json.dumps(
                                {"name": fn_name, "arguments": args_dict}
                            ),
                        }

                # ---- Run-item events (tool calls with structured data) ----
                elif event.type == "run_item_stream_event":
                    if event.name == "tool_called":
                        # Only emit if we haven't already sent this tool call
                        # from the raw response event above.
                        item = event.item
                        call_id = getattr(item, "call_id", None) or ""
                        if call_id and call_id in _emitted_tool_calls:
                            continue  # Already emitted from raw event

                        fn_name = getattr(item, "tool_name", None) or "unknown"
                        fn_args = {}
                        raw_item = getattr(item, "raw_item", None)
                        if raw_item is not None:
                            raw_args = getattr(raw_item, "arguments", "{}")
                            if isinstance(raw_args, str):
                                try:
                                    fn_args = json.loads(raw_args)
                                except (json.JSONDecodeError, TypeError):
                                    fn_args = {}

                        yield {
                            "event": "tool_call",
                            "data": json.dumps(
                                {"name": fn_name, "arguments": fn_args}
                            ),
                        }

                    # Function call arguments complete — emit tool_call event
                    elif (
                        hasattr(raw, "type")
                        and raw.type == "response.function_call_arguments.done"
                    ):
                        # Try to get the name from the event directly, then
                        # fall back to our tracked names from output_item.added.
                        fn_name = getattr(raw, "name", None)
                        if not fn_name:
                            call_id = getattr(raw, "call_id", None)
                            if call_id and call_id in _pending_tool_names:
                                fn_name = _pending_tool_names.pop(call_id)
                        if not fn_name:
                            fn_name = "unknown"

                        fn_args = getattr(raw, "arguments", "{}")
                        try:
                            args_dict = (
                                json.loads(fn_args)
                                if isinstance(fn_args, str)
                                else {}
                            )
                        except (json.JSONDecodeError, TypeError):
                            args_dict = {}
                        yield {
                            "event": "tool_call",
                            "data": json.dumps(
                                {"name": fn_name, "arguments": args_dict}
                            ),
                        }

                # ---- Run-item events (tool calls, messages) ----
                elif event.type == "run_item_stream_event":
                    item = event.item
                    if item.type == "tool_call_item":
                        fn_name = item.tool_name
                        if fn_name:
                            call_id = item.call_id
                            if call_id:
                                _pending_tool_names[call_id] = fn_name

                # ---- Agent updated event ----
                elif event.type == "agent_updated_stream_event":
                    pass

            # Stream finished — check for approval interruptions
            state = result.to_state()
            interruptions = state.get_interruptions()

            if interruptions:
                # Store state for later approval/rejection
                state_id = store_state(state, session_id)
                # Update the session's pending state
                session["pending_state"] = state_id

                preview = format_approval_preview(interruptions)
                yield {
                    "event": "approval_needed",
                    "data": json.dumps(
                        {"preview": preview, "state_id": state_id}
                    ),
                }
            else:
                # No interruptions — save assistant response to session
                final_output = getattr(result, "final_output", "") or assistant_text
                session["messages"].append(
                    {"role": "assistant", "content": str(final_output)}
                )
                yield {"event": "done", "data": "{}"}

        except Exception as exc:
            # CHAT-04: catch exceptions and return a natural-language message
            logger.exception("Error during chat stream")
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "message": "I'm sorry, something went wrong. Please try again."
                    }
                ),
            }

    return EventSourceResponse(event_generator())


# ---------------------------------------------------------------------------
# POST /chat/approve — confirm or reject a pending write
# ---------------------------------------------------------------------------


@router.post("/approve")
async def chat_approve(request: Request, body: ApproveRequest):
    """Confirm or reject a pending write operation.

    When the agent pauses for approval, the frontend calls this endpoint
    with the state_id from the approval_needed event.
    """
    store = _get_store(request)

    try:
        session = store.get(body.session_id)
        if session is None:
            return {"error": "Session not found or expired. Please start a new conversation."}

        # Load stored state
        state = load_state(body.state_id, finance_agent)
        if state is None:
            return {"error": "Approval state not found or expired. Please try your request again."}

        # Approve or reject each interruption
        interruptions = state.get_interruptions()
        if body.approved:
            for interruption in interruptions:
                state.approve(interruption)
        else:
            for interruption in interruptions:
                state.reject(interruption)

        # Resume the agent
        result = await Runner.run(
            finance_agent,
            state,
            context=session["client"],
        )

        # Update session history with the agent's final response
        response_text = str(getattr(result, "final_output", ""))
        session["messages"].append({"role": "assistant", "content": response_text})
        session["pending_state"] = None

        return {"response": response_text, "session_id": body.session_id}

    except Exception as exc:
        # CHAT-04: never expose stack traces
        logger.exception("Error during approval flow")
        return {
            "error": "I'm sorry, something went wrong processing your confirmation. Please try again."
        }