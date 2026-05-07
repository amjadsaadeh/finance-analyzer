---
phase: 01-agent-core-chat-interface
plan: 02
subsystem: api
tags: [fastapi, sse, sessions, approval-flow, human-in-the-loop]

# Dependency graph
requires:
  - phase: 01-agent-core-chat-interface
    provides: finance_agent definition with 13 function tools and needs_approval flags
provides:
  - FastAPI app with SSE streaming chat endpoint GET /chat/stream
  - Approval endpoint POST /chat/approve for confirm/reject of write operations
  - In-memory session store with TTL cleanup and per-session FireflyClient
  - Approval state management with store_state/load_state/format_approval_preview
  - Error handling that translates exceptions to natural language
affects: [01-03]

# Tech tracking
tech-stack:
  added: [fastapi==0.136.1, sse-starlette, uvicorn]
  patterns: [sse-streaming-via-EventSourceResponse, approval-pause-resume-via-RunState, session-scoped-context-with-FireflyClient, error-translation-to-natural-language]

key-files:
  created: [src/models.py, src/sessions.py, src/approval.py, src/app.py, src/chat.py, tests/test_chat.py]
  modified: [pyproject.toml, uv.lock]

key-decisions:
  - "Used session_id as state_id in approval store for simplicity — only one pending approval per session at a time"
  - "SSE error events use natural language messages (CHAT-04) — exceptions are caught and translated to user-friendly text, never exposing stack traces"
  - "Session store uses time.monotonic() for TTL — avoids clock skew issues with datetime.now()"
  - "Stored RunState as JSON via SDK serialization — allows resuming agent after approval"

patterns-established:
  - "SSE event types: text, tool_call, approval_needed, done, error — simple names for frontend parsing"
  - "Session data structure: {messages, client, created_at, _accessed_at, pending_state} — client is per-session FireflyClient"
  - "Approval preview format: {previews: [{tool_name, arguments, summary}], count} — structured for frontend rendering"
  - "Error events in SSE: caught exceptions produce {'event':'error', 'data':{'message':'natural language'}} — no technical details exposed"

requirements-completed: [CHAT-01, CHAT-02, CHAT-03, CHAT-04, SAFE-01, SAFE-02]

# Metrics
duration: 21min
completed: 2026-05-07
---

# Phase 1 Plan 2: Chat Server Summary

**FastAPI chat server with SSE streaming, session-scoped conversation context, and human-in-the-loop approval flow for data modifications**

## Performance

- **Duration:** 21 min
- **Started:** 2026-05-07T09:07:57Z
- **Completed:** 2026-05-07T09:29:56Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- Created FastAPI app with health check, CORS, static files mount, and chat router
- Implemented SSE streaming endpoint (GET /chat/stream) that invokes the agent via Runner.run_streamed and emits text, tool_call, approval_needed, done, and error events
- Built session-scoped SessionStore with per-session FireflyClient instances, TTL cleanup, and asyncio.Lock support
- Implemented approval flow (POST /chat/approve) that loads stored RunState, calls approve/reject on interruptions, and resumes the agent
- Error handling catches exceptions and translates them to natural language (CHAT-04) — never exposes stack traces

## Task Commits

Each task was committed atomically:

1. **Task 1: Create FastAPI app, models, session store, and SSE streaming endpoint** - `1398f8f` (feat)
2. **Task 2: Create approval endpoint and write chat tests** - `76e9216` (feat)

## Files Created/Modified
- `src/models.py` - Pydantic models: ChatRequest, ChatStreamRequest, ApproveRequest
- `src/sessions.py` - SessionStore with TTL cleanup, per-session FireflyClient, asyncio.Lock
- `src/approval.py` - store_state/load_state with TTL, format_approval_preview for interruptions
- `src/app.py` - FastAPI app with lifespan, CORS, health check, static files, chat router
- `src/chat.py` - SSE streaming endpoint (GET /chat/stream) and approval endpoint (POST /chat/approve)
- `tests/test_chat.py` - 23 tests: session store, approval flow, chat endpoints, models
- `pyproject.toml` - Added fastapi, sse-starlette, uvicorn dependencies
- `uv.lock` - Lockfile updated

## Decisions Made
- **session_id as state_id**: Used session_id as the key for approval state storage since only one pending approval per session makes sense (simplified from UUID state_id). Reduces complexity — no need to map state IDs back to sessions.
- **Natural language error events**: All exceptions in the SSE generator are caught and translated to user-friendly messages. Never exposes RuntimeError, ValueError, or stack traces to the client.
- **time.monotonic() for TTL**: Used monotonic clock instead of datetime.now() to avoid clock skew issues on session/access timestamps.
- **RunState JSON serialization**: The Agents SDK's built-in to_json()/from_json() serialization for RunState allows storing and resuming agent state across HTTP requests.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed SSE closure variable capture for FireflyClient error**
- **Found during:** Task 1 (chat endpoint creation)
- **Issue:** The `_error_gen` async generator captured the `exc` variable from a try/except block, but Python closure rules prevent accessing a deleted variable in an async generator — caused NameError when FireflyClient env vars were missing
- **Fix:** Captured `exc` into a local string `error_msg` before yielding, avoiding the closure issue
- **Files modified:** src/chat.py
- **Verification:** SSE endpoint returns graceful error event instead of 500 crash
- **Committed in:** 1398f8f (Task 1 commit)

**2. [Rule 2 - Missing Critical] Added graceful error handling for missing FireflyClient env vars**
- **Found during:** Task 1 (SSE endpoint verification)
- **Issue:** When FIREFLY_BASE_URL/FIREFLY_API_TOKEN are not set, the endpoint crashed with a stack trace instead of returning a user-friendly SSE error event
- **Fix:** Added try/except around get_or_create_session in chat_stream to catch ValueError/EnvironmentError and return an SSE error event with a natural language message
- **Files modified:** src/chat.py
- **Verification:** curl test shows clean SSE error event: `event: error\ndata: {"message":"Server configuration error..."}`
- **Committed in:** 1398f8f (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 bug, 1 missing critical)
**Impact on plan:** Both fixes essential for error handling requirement (CHAT-04). No scope creep.

## Issues Encountered
None — all deviations were auto-fixed and documented above.

## User Setup Required
None - no external service configuration required for the server code. Environment variables FIREFLY_BASE_URL and FIREFLY_API_TOKEN are needed at runtime (already required by tools.py).

## Next Phase Readiness
- Chat server with SSE streaming and approval flow complete, ready for Plan 03 (chat frontend/UI)
- `src/app.py` exports `app` for uvicorn entry point
- `src/chat.py` provides `chat_stream` and `chat_approve` endpoints
- `src/approval.py` provides state management for approval pause/resume
- All 65 tests pass (42 existing + 23 new)

## Self-Check: PASSED

- src/models.py: FOUND
- src/sessions.py: FOUND
- src/approval.py: FOUND
- src/app.py: FOUND
- src/chat.py: FOUND
- tests/test_chat.py: FOUND
- Task 1 commit (1398f8f): FOUND
- Task 2 commit (76e9216): FOUND
- All 65 tests pass: CONFIRMED

---
*Phase: 01-agent-core-chat-interface*
*Completed: 2026-05-07*