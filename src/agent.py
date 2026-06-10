"""Finance Analyzer agent definition for the OpenAI Agents SDK.

Defines the Finance Assistant agent with 13 function tools wrapping the
existing Firefly III dispatch system, a system prompt enforcing data-first
responses, and approval flags on write operations.
"""

import json
from datetime import date, datetime
from typing import Any

from agents import Agent, RunContextWrapper, function_tool

from src.tools import FireflyClient, dispatch


def _json_serialize(obj: Any) -> str:
    """Serialize a dispatch result dict to JSON, converting datetime/date to ISO strings.

    The Firefly III API client returns datetime objects (not strings) in
    transaction data. Standard json.dumps() raises TypeError on these.
    """
    return json.dumps(obj, default=_json_default)


def _json_default(obj: Any) -> str:
    """Handle non-JSON-serializable types from Firefly III data."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

current_date = date.today().isoformat()

SYSTEM_PROMPT = f"""\
You are a personal finance assistant connected to a Firefly III budgeting \
system. You help users understand their spending, income, and financial patterns.

RULES:
1. NEVER calculate or estimate monetary values yourself. Always use \
sum_transactions, calculate_net, or compare_periods tools for any arithmetic. \
All dollar amounts must come directly from tool call results.
2. When a tool returns an "error" key, explain what went wrong in plain \
language. Never show raw error messages, API codes, or technical details to \
the user.
3. For date ranges, use YYYY-MM-DD format. When the user says "last month", \
calculate the exact date range for the previous calendar month.
4. Be concise. Lead with the answer, then show supporting detail if asked.
5. When you want to modify financial data (tags, categories), always describe \
what you plan to change and wait for user confirmation.
6. To identify unnecessary or anomalous spending, use get_expense_insights, \
compare_periods, and list_transactions to find categories or transactions \
that stand out from normal patterns.\

The current date is {current_date}. Always use this to interpret relative date references like \
"last month" or "past 7 days".
"""

# ---------------------------------------------------------------------------
# Helper: extract FireflyClient from agent context
# ---------------------------------------------------------------------------


def _get_client(ctx: RunContextWrapper[FireflyClient]) -> FireflyClient:
    """Retrieve the FireflyClient from the run context."""
    return ctx.context


# ---------------------------------------------------------------------------
# Read tools (no approval needed)
# ---------------------------------------------------------------------------


@function_tool
async def list_transactions(
    ctx: RunContextWrapper[FireflyClient],
    limit: int = 50,
    page: int = 1,
) -> str:
    """List transactions from Firefly III. Results are paginated; use the \
page parameter to retrieve subsequent pages."""
    client = _get_client(ctx)
    result = dispatch(client, "list_transactions", {"limit": limit, "page": page})
    return _json_serialize(result)


@function_tool
async def get_transactions_by_date_range(
    ctx: RunContextWrapper[FireflyClient],
    start_date: str,
    end_date: str,
    limit: int = 50,
    page: int = 1,
) -> str:
    """List transactions between start_date and end_date (YYYY-MM-DD format). \
Results are paginated; increase page to retrieve more."""
    client = _get_client(ctx)
    result = dispatch(
        client,
        "get_transactions_by_date_range",
        {"start_date": start_date, "end_date": end_date, "limit": limit, "page": page},
    )
    return _json_serialize(result)


@function_tool
async def search_transactions(
    ctx: RunContextWrapper[FireflyClient],
    query: str,
    limit: int = 50,
    page: int = 1,
) -> str:
    """Full-text search across transaction descriptions."""
    client = _get_client(ctx)
    result = dispatch(
        client,
        "search_transactions",
        {"query": query, "limit": limit, "page": page},
    )
    return _json_serialize(result)


@function_tool
async def list_accounts(
    ctx: RunContextWrapper[FireflyClient],
    account_type: str | None = None,
    limit: int = 50,
    page: int = 1,
) -> str:
    """List all accounts with their current balances. Optionally filter by \
account type (e.g. asset, expense, revenue, liability, cash)."""
    args: dict[str, Any] = {"limit": limit, "page": page}
    if account_type is not None:
        args["account_type"] = account_type
    client = _get_client(ctx)
    result = dispatch(client, "list_accounts", args)
    return _json_serialize(result)


@function_tool
async def get_expense_insights(
    ctx: RunContextWrapper[FireflyClient],
    start_date: str,
    end_date: str,
    account_ids: list[int] | None = None,
) -> str:
    """Get expense totals grouped by category for a date range. Useful for \
understanding where money went."""
    args: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    if account_ids is not None:
        args["account_ids"] = account_ids
    client = _get_client(ctx)
    result = dispatch(client, "get_expense_insights", args)
    return _json_serialize(result)


@function_tool
async def get_income_insights(
    ctx: RunContextWrapper[FireflyClient],
    start_date: str,
    end_date: str,
    account_ids: list[int] | None = None,
) -> str:
    """Get income totals grouped by category for a date range."""
    args: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    if account_ids is not None:
        args["account_ids"] = account_ids
    client = _get_client(ctx)
    result = dispatch(client, "get_income_insights", args)
    return _json_serialize(result)


@function_tool
async def list_categories(
    ctx: RunContextWrapper[FireflyClient],
    limit: int = 50,
    page: int = 1,
) -> str:
    """List all transaction categories."""
    client = _get_client(ctx)
    result = dispatch(client, "list_categories", {"limit": limit, "page": page})
    return _json_serialize(result)


@function_tool
async def list_tags(
    ctx: RunContextWrapper[FireflyClient],
    limit: int = 50,
    page: int = 1,
) -> str:
    """List all transaction tags."""
    client = _get_client(ctx)
    result = dispatch(client, "list_tags", {"limit": limit, "page": page})
    return _json_serialize(result)


@function_tool(strict_mode=False)
async def sum_transactions(
    ctx: RunContextWrapper[FireflyClient],
    transactions: list[dict[str, Any]],
) -> str:
    """Sum transaction amounts from a list already returned by a previous \
tool call. Use this instead of doing arithmetic yourself to avoid \
floating-point errors. Returns totals split by transaction type \
(deposit=income, withdrawal=expense, transfer=neutral)."""
    client = _get_client(ctx)
    result = dispatch(client, "sum_transactions", {"transactions": transactions})
    return _json_serialize(result)


@function_tool
async def calculate_net(
    ctx: RunContextWrapper[FireflyClient],
    start_date: str,
    end_date: str,
    account_ids: list[int] | None = None,
) -> str:
    """Calculate net cash flow (total income minus total expenses) for a \
date range. Fetches expense and income insight totals from Firefly III \
and subtracts to produce net."""
    args: dict[str, Any] = {"start_date": start_date, "end_date": end_date}
    if account_ids is not None:
        args["account_ids"] = account_ids
    client = _get_client(ctx)
    result = dispatch(client, "calculate_net", args)
    return _json_serialize(result)


@function_tool
async def compare_periods(
    ctx: RunContextWrapper[FireflyClient],
    period_a_start: str,
    period_a_end: str,
    period_b_start: str,
    period_b_end: str,
    account_ids: list[int] | None = None,
) -> str:
    """Compare income, expenses, and net cash flow between two date ranges. \
Returns totals for each period plus the absolute and percentage delta."""
    args: dict[str, Any] = {
        "period_a_start": period_a_start,
        "period_a_end": period_a_end,
        "period_b_start": period_b_start,
        "period_b_end": period_b_end,
    }
    if account_ids is not None:
        args["account_ids"] = account_ids
    client = _get_client(ctx)
    result = dispatch(client, "compare_periods", args)
    return _json_serialize(result)


# ---------------------------------------------------------------------------
# Write tools (require user approval — SAFE-01/SAFE-02)
# ---------------------------------------------------------------------------


@function_tool(needs_approval=True)
async def update_transaction_tags(
    ctx: RunContextWrapper[FireflyClient],
    transaction_id: str,
    tags: list[str],
) -> str:
    """Replace all tags on a transaction with a new list of tags. \
REQUIRES USER CONFIRMATION before applying changes."""
    client = _get_client(ctx)
    result = dispatch(
        client,
        "update_transaction_tags",
        {"transaction_id": transaction_id, "tags": tags},
    )
    return _json_serialize(result)


@function_tool(needs_approval=True)
async def update_transaction_category(
    ctx: RunContextWrapper[FireflyClient],
    transaction_id: str,
    category_name: str,
) -> str:
    """Set the category on a transaction. REQUIRES USER CONFIRMATION \
before applying changes."""
    client = _get_client(ctx)
    result = dispatch(
        client,
        "update_transaction_category",
        {"transaction_id": transaction_id, "category_name": category_name},
    )
    return _json_serialize(result)


# ---------------------------------------------------------------------------
# Agent definition
# ---------------------------------------------------------------------------

finance_agent = Agent(
    name="Finance Assistant",
    instructions=SYSTEM_PROMPT,
    tools=[
        list_transactions,
        get_transactions_by_date_range,
        search_transactions,
        update_transaction_tags,
        update_transaction_category,
        list_accounts,
        get_expense_insights,
        get_income_insights,
        list_categories,
        list_tags,
        sum_transactions,
        calculate_net,
        compare_periods,
    ],
)