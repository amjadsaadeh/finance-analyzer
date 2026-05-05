import os
import datetime

from firefly_iii_client.configuration import Configuration
from firefly_iii_client import ApiClient
from firefly_iii_client.api import (
    TransactionsApi,
    AccountsApi,
    CategoriesApi,
    TagsApi,
    SearchApi,
    InsightApi,
)
from firefly_iii_client.models import TransactionUpdate, TransactionSplitUpdate
from firefly_iii_client.exceptions import ApiException


class FireflyClient:
    def __init__(self, base_url: str | None = None, api_token: str | None = None):
        self.base_url = base_url or os.environ.get("FIREFLY_BASE_URL")
        self.api_token = api_token or os.environ.get("FIREFLY_API_TOKEN")
        if not self.base_url:
            raise ValueError("FIREFLY_BASE_URL must be set via env var or constructor argument")
        if not self.api_token:
            raise ValueError("FIREFLY_API_TOKEN must be set via env var or constructor argument")
        config = Configuration(host=self.base_url, access_token=self.api_token)
        self.api_client = ApiClient(configuration=config)


def _handler_list_transactions(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    try:
        resp = api.list_transaction(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_transactions_by_date_range(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    except ValueError as e:
        return {"error": f"Invalid date format: {e}"}
    try:
        resp = api.list_transaction(
            start=start,
            end=end,
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_search_transactions(client: FireflyClient, args: dict) -> dict:
    api = SearchApi(client.api_client)
    try:
        query = args["query"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    try:
        resp = api.search_transactions(
            query=query,
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _build_split_update(split, *, tags=None, category_name=None) -> TransactionSplitUpdate:
    return TransactionSplitUpdate(
        description=split.description,
        date=split.date,
        amount=str(split.amount),
        type=split.type,
        tags=tags if tags is not None else split.tags,
        category_name=category_name if category_name is not None else split.category_name,
        source_id=str(split.source_id) if split.source_id else None,
        destination_id=str(split.destination_id) if split.destination_id else None,
    )


def _handler_update_transaction_tags(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    try:
        tx_id = str(args["transaction_id"])
        tags = args["tags"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    try:
        existing = api.get_transaction(tx_id)
        splits = existing.data.attributes.transactions
        updated = [_build_split_update(s, tags=tags) for s in splits]
        result = api.update_transaction(tx_id, TransactionUpdate(transactions=updated))
        return result.data.to_dict()
    except ApiException as e:
        return {"error": str(e)}


def _handler_update_transaction_category(client: FireflyClient, args: dict) -> dict:
    api = TransactionsApi(client.api_client)
    try:
        tx_id = str(args["transaction_id"])
        category_name = args["category_name"]
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    try:
        existing = api.get_transaction(tx_id)
        splits = existing.data.attributes.transactions
        updated = [_build_split_update(s, category_name=category_name) for s in splits]
        result = api.update_transaction(tx_id, TransactionUpdate(transactions=updated))
        return result.data.to_dict()
    except ApiException as e:
        return {"error": str(e)}


def _handler_list_accounts(client: FireflyClient, args: dict) -> dict:
    api = AccountsApi(client.api_client)
    try:
        resp = api.list_account(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
            type=args.get("account_type"),
        )
        return {"accounts": [a.to_dict() for a in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_expense_insights(client: FireflyClient, args: dict) -> dict:
    api = InsightApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    except ValueError as e:
        return {"error": f"Invalid date format: {e}"}
    try:
        entries = api.insight_expense_category(
            start=start,
            end=end,
            accounts=args.get("account_ids"),
        )
        return {"insights": [entry.to_dict() for entry in entries]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_get_income_insights(client: FireflyClient, args: dict) -> dict:
    api = InsightApi(client.api_client)
    try:
        start = datetime.date.fromisoformat(args["start_date"])
        end = datetime.date.fromisoformat(args["end_date"])
    except KeyError as e:
        return {"error": f"Missing required argument: {e}"}
    except ValueError as e:
        return {"error": f"Invalid date format: {e}"}
    try:
        entries = api.insight_income_category(
            start=start,
            end=end,
            accounts=args.get("account_ids"),
        )
        return {"insights": [entry.to_dict() for entry in entries]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_list_categories(client: FireflyClient, args: dict) -> dict:
    api = CategoriesApi(client.api_client)
    try:
        resp = api.list_category(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"categories": [c.to_dict() for c in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


def _handler_list_tags(client: FireflyClient, args: dict) -> dict:
    api = TagsApi(client.api_client)
    try:
        resp = api.list_tag(
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"tags": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


_HANDLERS: dict = {
    "list_transactions": _handler_list_transactions,
    "get_transactions_by_date_range": _handler_get_transactions_by_date_range,
    "search_transactions": _handler_search_transactions,
    "update_transaction_tags": _handler_update_transaction_tags,
    "update_transaction_category": _handler_update_transaction_category,
    "list_accounts": _handler_list_accounts,
    "get_expense_insights": _handler_get_expense_insights,
    "get_income_insights": _handler_get_income_insights,
    "list_categories": _handler_list_categories,
    "list_tags": _handler_list_tags,
}
TOOLS: list = [
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": "List transactions from Firefly III with optional filters. Results are paginated (default 50 per page); use the page parameter to retrieve subsequent pages.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_transactions_by_date_range",
            "description": "List transactions between start_date and end_date (YYYY-MM-DD format). Results are paginated; increase page to retrieve more.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_transactions",
            "description": "Full-text search across transaction descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query string"},
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction_tags",
            "description": "Replace all tags on a transaction with a new list of tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string", "description": "ID of the transaction"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New list of tags (replaces existing tags)",
                    },
                },
                "required": ["transaction_id", "tags"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_transaction_category",
            "description": "Set the category on a transaction.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transaction_id": {"type": "string", "description": "ID of the transaction"},
                    "category_name": {"type": "string", "description": "Category name to assign"},
                },
                "required": ["transaction_id", "category_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_accounts",
            "description": "List all accounts with their current balances.",
            "parameters": {
                "type": "object",
                "properties": {
                    "account_type": {
                        "type": "string",
                        "description": "Filter by account type, e.g. asset, expense, revenue, liability, cash, liabilities (optional — omit for all)",
                    },
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_expense_insights",
            "description": "Get expense totals grouped by category for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "account_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Filter by account IDs (optional)",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_income_insights",
            "description": "Get income totals grouped by category for a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                    "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"},
                    "account_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Filter by account IDs (optional)",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List all transaction categories.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tags",
            "description": "List all transaction tags.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max results per page (default 50)"},
                    "page": {"type": "integer", "description": "Page number (default 1)"},
                },
                "required": [],
            },
        },
    },
]


def dispatch(client: FireflyClient, tool_name: str, args: dict) -> dict:
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return handler(client, args)


def get_tools() -> list:
    return TOOLS
