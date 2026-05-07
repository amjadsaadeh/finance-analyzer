"""Tests for the Finance Analyzer agent configuration.

Verifies:
- 13 tools registered with correct names
- Write tools have needs_approval=True
- Read tools have needs_approval=False
- System prompt contains required rules
- Tool wrappers correctly call dispatch()
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from agents import RunContextWrapper
from agents.tool_context import ToolContext

from src.agent import (
    SYSTEM_PROMPT,
    calculate_net,
    compare_periods,
    finance_agent,
    get_expense_insights,
    get_income_insights,
    get_transactions_by_date_range,
    list_accounts,
    list_categories,
    list_tags,
    list_transactions,
    search_transactions,
    sum_transactions,
    update_transaction_category,
    update_transaction_tags,
)
from tools import FireflyClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx() -> ToolContext:
    """Create a ToolContext wrapping a mock FireflyClient.

    Uses a real ToolContext (which extends RunContextWrapper) so the
    SDK's on_invoke_tool can access ctx.tool_name, etc.
    """
    mock_client = MagicMock(spec=FireflyClient)
    return ToolContext(
        context=mock_client,
        tool_name="test_tool",
        tool_call_id="call_test",
        tool_arguments="{}",
    )


# ---------------------------------------------------------------------------
# 1. Tool registration tests
# ---------------------------------------------------------------------------


EXPECTED_TOOL_NAMES = {
    "list_transactions",
    "get_transactions_by_date_range",
    "search_transactions",
    "update_transaction_tags",
    "update_transaction_category",
    "list_accounts",
    "get_expense_insights",
    "get_income_insights",
    "list_categories",
    "list_tags",
    "sum_transactions",
    "calculate_net",
    "compare_periods",
}


def test_agent_has_exactly_13_tools():
    """The finance_agent must register exactly 13 tools."""
    assert len(finance_agent.tools) == 13


def test_agent_tool_names_are_expected():
    """All 13 expected tool names must be present on the agent."""
    actual = {t.name for t in finance_agent.tools}
    assert actual == EXPECTED_TOOL_NAMES


# ---------------------------------------------------------------------------
# 2. Approval flag tests
# ---------------------------------------------------------------------------


WRITE_TOOLS = {"update_transaction_tags", "update_transaction_category"}
READ_TOOLS = EXPECTED_TOOL_NAMES - WRITE_TOOLS


def test_write_tools_need_approval():
    """Write tools (tag/category updates) must have needs_approval=True."""
    for tool in finance_agent.tools:
        if tool.name in WRITE_TOOLS:
            assert tool.needs_approval is True, (
                f"Write tool {tool.name} should need approval"
            )


def test_read_tools_do_not_need_approval():
    """Read-only tools must have needs_approval=False."""
    for tool in finance_agent.tools:
        if tool.name in READ_TOOLS:
            assert tool.needs_approval is False, (
                f"Read tool {tool.name} should not need approval"
            )


# ---------------------------------------------------------------------------
# 3. System prompt content tests
# ---------------------------------------------------------------------------


def test_system_prompt_has_no_calculation_rule():
    """System prompt must forbid LLM arithmetic and name the correct tools."""
    assert "sum_transactions" in SYSTEM_PROMPT
    assert "calculate_net" in SYSTEM_PROMPT
    assert "compare_periods" in SYSTEM_PROMPT


def test_system_prompt_has_error_translation_rule():
    """System prompt must instruct LLM to translate error keys to plain language."""
    assert "error" in SYSTEM_PROMPT.lower()
    assert "plain language" in SYSTEM_PROMPT.lower()


def test_system_prompt_has_date_format_rule():
    """System prompt must specify YYYY-MM-DD date format."""
    assert "YYYY-MM-DD" in SYSTEM_PROMPT


def test_system_prompt_has_approval_rule():
    """System prompt must instruct LLM to seek confirmation before modifying data."""
    assert "confirmation" in SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# 4. Dispatch wrapping test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_wrapper_calls_dispatch():
    """Tool wrappers must call dispatch(client, tool_name, args) and return JSON."""
    mock_result = {"transactions": [{"id": "42", "description": "Test transaction"}]}

    with patch("src.agent.dispatch", return_value=mock_result) as mock_dispatch:
        ctx = _make_ctx()

        result = await list_transactions.on_invoke_tool(ctx, json.dumps({"limit": 50, "page": 1}))

        mock_dispatch.assert_called_once_with(
            ctx.context,
            "list_transactions",
            {"limit": 50, "page": 1},
        )
        assert json.loads(result) == mock_result


@pytest.mark.asyncio
async def test_tool_wrapper_passes_all_args():
    """Tool wrapper must forward all provided arguments to dispatch."""
    mock_result = {"transactions": []}

    with patch("src.agent.dispatch", return_value=mock_result) as mock_dispatch:
        ctx = _make_ctx()

        result = await get_transactions_by_date_range.on_invoke_tool(
            ctx,
            json.dumps({"start_date": "2025-01-01", "end_date": "2025-01-31", "limit": 10, "page": 2}),
        )

        mock_dispatch.assert_called_once_with(
            ctx.context,
            "get_transactions_by_date_range",
            {"start_date": "2025-01-01", "end_date": "2025-01-31", "limit": 10, "page": 2},
        )
        assert json.loads(result) == mock_result


@pytest.mark.asyncio
async def test_write_tool_wrapper_calls_dispatch():
    """Write tool wrappers must call dispatch and return JSON."""
    mock_result = {"id": "42", "tags": ["food", "dining"]}

    with patch("src.agent.dispatch", return_value=mock_result) as mock_dispatch:
        ctx = _make_ctx()

        result = await update_transaction_tags.on_invoke_tool(
            ctx,
            json.dumps({"transaction_id": "42", "tags": ["food", "dining"]}),
        )

        mock_dispatch.assert_called_once_with(
            ctx.context,
            "update_transaction_tags",
            {"transaction_id": "42", "tags": ["food", "dining"]},
        )
        assert json.loads(result) == mock_result