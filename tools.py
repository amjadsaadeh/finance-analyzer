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
        resp = api.list_transaction(
            start=start,
            end=end,
            limit=args.get("limit", 50),
            page=args.get("page", 1),
        )
        return {"transactions": [t.to_dict() for t in resp.data]}
    except ApiException as e:
        return {"error": str(e)}


_HANDLERS: dict = {
    "list_transactions": _handler_list_transactions,
    "get_transactions_by_date_range": _handler_get_transactions_by_date_range,
}
TOOLS: list = []


def dispatch(client: FireflyClient, tool_name: str, args: dict) -> dict:
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return {"error": f"Unknown tool: {tool_name}"}
    return handler(client, args)


def get_tools() -> list:
    return TOOLS
