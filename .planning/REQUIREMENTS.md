# Requirements: Finance Analyzer

**Defined:** 2026-05-06
**Core Value:** Turning raw transaction data into actionable financial insight through natural conversation — LLM understands context, learns from corrections, and gives advice you can act on.

## v1 Requirements

### Chat Interface

- [ ] **CHAT-01**: User can interact via web-based chat interface served by FastAPI
- [ ] **CHAT-02**: Chat displays LLM responses in real-time via SSE streaming
- [ ] **CHAT-03**: Chat maintains session-scoped conversation context (remember date ranges, categories, filters within a session)
- [ ] **CHAT-04**: Chat gracefully handles errors — missing data, API failures, and invalid queries return natural language explanations, not stack traces

### Tool Routing

- [x] **TOOL-01**: LLM routes natural language questions to existing Firefly III tools (list, search, filter, insights, net, compare)
- [x] **TOOL-02**: LLM answers spending questions with real transaction data ("How much did I spend on hobbies last month?")
- [x] **TOOL-03**: LLM identifies unnecessary or anomalous spending when asked ("Which expenses weren't necessary?")
- [x] **TOOL-04**: All numeric results come from tool calls (Decimal precision), never from LLM calculation

### Categorization

- [ ] **CAT-01**: System auto-categorizes uncategorized transactions based on description, date, and account name
- [ ] **CAT-02**: System presents proposed categorizations for user review before applying
- [ ] **CAT-03**: User can correct categorizations through chat, and the system re-evaluates its categorization logic (not rigid memorization)

### Reports & Insights

- [ ] **RPT-01**: System generates savings reports covering 3-6 month trends with embedded charts/tables
- [ ] **RPT-02**: Reports include written narrative insights ("Your dining spending increased 40% over 3 months, driven by...")
- [ ] **RPT-03**: Reports suggest concrete, data-backed actions ("Consider capping dining at $200/mo — you averaged $350/mo over 6 months")

### Write Safety

- [ ] **SAFE-01**: All financial data modifications (tags, categories) require explicit user confirmation before applying
- [ ] **SAFE-02**: System previews proposed changes before confirmation ("I'll categorize 5 transactions as Groceries. Confirm?")

## v2 Requirements

### Advanced Insights

- **INS-02**: System proactively flags anomalous spending patterns when session starts ("Your utilities were 3x the 6-month average")
- **INS-03**: System suggests new categories for uncategorized transaction patterns ("You have 15 transactions that could be a 'Home Office' category")

### Enhanced Categorization

- **CAT-04**: System detects and highlights recurring expenses in chat
- **CAT-05**: Correction learning persists across sessions

### Report Exports

- **RPT-04**: Export savings reports as shareable documents

## Out of Scope

| Feature | Reason |
|---------|--------|
| Budget creation/enforcement | Firefly III has its own budget system; this tool informs decisions, doesn't enforce |
| Bank feed syncing | Firefly III's data importer handles this; duplicating would be massive scope |
| Investment/portfolio tracking | Separate domain from spending analysis with different data sources |
| Multi-user/household sharing | Personal single-instance use only; multi-tenancy is massive complexity |
| Licensed financial advice | Regulatory landmine; stick to descriptive analysis and behavioral suggestions |
| Dashboard/charting engine | Chat-first is the differentiator; charts only in reports, not as primary interface |
| Persistent cross-session memory | Session-scoped context only; privacy and consistency concerns |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CHAT-01 | Phase 1: Agent Core & Chat Interface | Pending |
| CHAT-02 | Phase 1: Agent Core & Chat Interface | Pending |
| CHAT-03 | Phase 1: Agent Core & Chat Interface | Pending |
| CHAT-04 | Phase 1: Agent Core & Chat Interface | Pending |
| TOOL-01 | Phase 1: Agent Core & Chat Interface | Complete |
| TOOL-02 | Phase 1: Agent Core & Chat Interface | Complete |
| TOOL-03 | Phase 1: Agent Core & Chat Interface | Complete |
| TOOL-04 | Phase 1: Agent Core & Chat Interface | Complete |
| SAFE-01 | Phase 1: Agent Core & Chat Interface | Pending |
| SAFE-02 | Phase 1: Agent Core & Chat Interface | Pending |
| CAT-01 | Phase 2: Auto-Categorization & Learning | Pending |
| CAT-02 | Phase 2: Auto-Categorization & Learning | Pending |
| CAT-03 | Phase 2: Auto-Categorization & Learning | Pending |
| RPT-01 | Phase 3: Narrative Savings Reports | Pending |
| RPT-02 | Phase 3: Narrative Savings Reports | Pending |
| RPT-03 | Phase 3: Narrative Savings Reports | Pending |

**Coverage:**
- v1 requirements: 16 total
- Mapped to phases: 16
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-06*
*Last updated: 2026-05-06 after roadmap creation*