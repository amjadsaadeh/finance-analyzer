---
status: resolved
trigger: "Approval flow crashes with AttributeError + shows '?' for transaction/category"
created: 2026-05-08T10:00:00Z
updated: 2026-05-08T11:00:00Z
---

## Current Focus

hypothesis: CONFIRMED — multiple bugs in approval flow
test: manual + automated tests
expecting: all pass
next_action: complete — user to re-test

## Symptoms

expected: Approval confirm resumes the LLM and applies changes; preview shows actual transaction IDs and category names
actual: AttributeError on RunState.starting_agent; approval preview shows "?" for all fields
errors: "AttributeError: 'RunState' object has no attribute 'starting_agent'. Did you mean: '_starting_agent'?"
reproduction: Click Confirm on approval panel, or trigger approval preview for data modification
started: UAT test 6

## Eliminated

- hypothesis: Runner.run needs starting_agent from stored state
  evidence: load_state already receives starting_agent as parameter; not needed in stored dict
  timestamp: 2026-05-08T10:15:00Z

## Evidence

- timestamp: 2026-05-08T10:05:00Z
  checked: OpenAI Agents SDK RunState class attributes
  found: RunState uses _starting_agent (private), not starting_agent. from_json() is async (returns coroutine if not awaited)
  implication: store_state accesses wrong attribute; load_state doesn't await from_json

- timestamp: 2026-05-08T10:10:00Z
  checked: ToolApprovalItem.arguments property type
  found: ToolApprovalItem.arguments returns str | None (JSON string), never dict
  implication: format_approval_preview treats it as dict, always falls through to {} → all field lookups return "?"

- timestamp: 2026-05-08T10:30:00Z
  checked: All 79 tests pass after fixes
  found: All pass, including async load_state tests
  implication: Fixes are correct

## Resolution

root_cause: Three bugs:
1. store_state accessed state.starting_agent (private attr _starting_agent) — removed from stored dict since load_state receives it as param
2. RunState.from_json() is async but load_state() called it synchronously — made load_state async with await
3. ToolApprovalItem.arguments is str (JSON) not dict — added json.loads() parsing in format_approval_preview

fix: 
- src/approval.py: removed starting_agent from stored dict, made load_state async, added JSON string parsing
- src/chat.py: added await to load_state call
- tests: updated mocks to use AsyncMock, JSON string arguments

verification: 79 tests passing, user to verify end-to-end
files_changed:
  - src/approval.py
  - src/chat.py
  - tests/test_chat.py
  - tests/test_integration.py