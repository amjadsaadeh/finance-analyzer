# Roadmap: Finance Analyzer

## Overview

Build an LLM-powered personal finance analyzer in three phases: first establish the foundational agent loop and chat interface so users can ask finance questions and get accurate, tool-backed answers; then add auto-categorization with learning-from-corrections so the system can classify transactions intelligently; finally deliver narrative savings reports with actionable recommendations backed by real data.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Agent Core & Chat Interface** — Users can ask finance questions through web chat and receive accurate, tool-backed answers streamed in real-time
- [ ] **Phase 2: Auto-Categorization & Learning** — Users can auto-categorize uncategorized transactions and teach the system through corrections that re-evaluate patterns
- [ ] **Phase 3: Narrative Savings Reports** — Users can generate savings reports combining narrative insights with data-backed actionable recommendations

## Phase Details

### Phase 1: Agent Core & Chat Interface
**Goal**: Users can ask finance questions through a web chat and receive accurate, tool-backed answers streamed in real-time, with safe handling of any data modifications
**Depends on**: Nothing (first phase)
**Requirements**: CHAT-01, CHAT-02, CHAT-03, CHAT-04, TOOL-01, TOOL-02, TOOL-03, TOOL-04, SAFE-01, SAFE-02
**Success Criteria** (what must be TRUE):
  1. User opens chat in browser, types a spending question, and receives a streaming response with real data from Firefly III
  2. User asks follow-up questions referencing earlier conversation context, and the LLM understands the reference (e.g., "what about last month?" after asking about dining spending)
  3. User asks about spending patterns or specific categories, and the LLM routes to the correct Firefly III tools — all numbers come from tool calls, never from LLM calculation
  4. When the LLM proposes a data modification (tag, category), user sees a preview of changes and must explicitly confirm before anything is applied
  5. When API calls fail or data is missing, user sees a natural language explanation instead of a stack trace or raw error
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — Agent definition with system prompt and 13 function tools wrapping dispatch()
- [ ] 01-02-PLAN.md — FastAPI chat server with SSE streaming, sessions, and approval flow
- [ ] 01-03-PLAN.md — Chat frontend UI, uvicorn entry point, and end-to-end integration

### Phase 2: Auto-Categorization & Learning
**Goal**: Users can auto-categorize uncategorized transactions and teach the system through corrections that re-evaluate categorization patterns rather than rigidly memorizing
**Depends on**: Phase 1
**Requirements**: CAT-01, CAT-02, CAT-03
**Success Criteria** (what must be TRUE):
  1. User asks to categorize uncategorized transactions, and the system proposes categorizations based on transaction description, date, and account name
  2. User reviews proposed categorizations before they are applied — nothing is written to Firefly III without explicit confirmation
  3. User corrects a categorization through chat, and the system adjusts future categorizations by re-evaluating its logic rather than rigidly memorizing the single correction
**Plans**: TBD

Plans:
- [ ] 02-01: TBD
- [ ] 02-02: TBD

### Phase 3: Narrative Savings Reports
**Goal**: Users can generate savings reports that combine written narrative insights with data-backed, actionable recommendations over 3-6 month trends
**Depends on**: Phase 2
**Requirements**: RPT-01, RPT-02, RPT-03
**Success Criteria** (what must be TRUE):
  1. User requests a savings report, and the system generates a report covering 3-6 month trends with embedded charts and tables
  2. Reports include written narrative insights that explain spending patterns and changes over time (e.g., "Your dining spending increased 40% over 3 months, driven by...")
  3. Reports suggest concrete, data-backed actions (e.g., "Consider capping dining at $200/mo — you averaged $350/mo over 6 months")
**Plans**: TBD

Plans:
- [ ] 03-01: TBD
- [ ] 03-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Agent Core & Chat Interface | 0/3 | Ready to execute | - |
| 2. Auto-Categorization & Learning | 0/? | Not started | - |
| 3. Narrative Savings Reports | 0/? | Not started | - |