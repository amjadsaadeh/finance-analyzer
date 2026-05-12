"""Integration tests for tools.py against a real Firefly III instance.

Two ways to run:

  # Spin up Docker automatically (requires Docker + docker compose):
  uv run pytest tests/test_integration.py --run-integration

  # Point at an already-running instance:
  FIREFLY_TEST_URL=http://localhost:8080/api \\
  FIREFLY_TEST_TOKEN=<pat> \\
  uv run pytest tests/test_integration.py
"""

import datetime
import os
import re
import subprocess
import textwrap
import time
import urllib.error
import urllib.request
import uuid

import pytest

from tools import FireflyClient, dispatch

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_COMPOSE_FILE = os.path.join(os.path.dirname(__file__), "docker-compose.firefly.yml")
_PORT = 18080


# ---------------------------------------------------------------------------
# Docker / environment lifecycle
# ---------------------------------------------------------------------------

def _wait_for_firefly(base_url: str, timeout: int = 180) -> None:
    """Poll /api/v1/about until the app responds (401 = app up, auth required)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(
                urllib.request.Request(f"{base_url}/api/v1/about"), timeout=3
            )
            return  # 200 — unexpected but fine
        except urllib.error.HTTPError as exc:
            if exc.code == 401:
                return  # auth required → app is fully up
        except Exception:
            pass
        time.sleep(3)
    raise TimeoutError(f"Firefly III did not become ready within {timeout}s at {base_url}")


def _bootstrap_token(compose_file: str, project: str) -> str:
    """Create an admin user inside the container and return a Personal Access Token."""
    php = textwrap.dedent("""\
        $u = \\FireflyIII\\User::firstOrCreate(
            ['email' => 'admin@inttest.local'],
            ['password' => bcrypt('inttest'), 'blocked' => 0]
        );
        $role = \\Spatie\\Permission\\Models\\Role::firstOrCreate(
            ['name' => 'owner', 'guard_name' => 'web']
        );
        if (!$u->hasRole('owner')) { $u->assignRole($role); }
        echo '>>>T_S<<<' . $u->createToken('ci')->accessToken . '>>>T_E<<<';
    """)
    result = subprocess.run(
        [
            "docker", "compose", "-f", compose_file, "-p", project,
            "exec", "-T", "firefly_app", "php", "artisan", "tinker",
        ],
        input=php.encode(),
        capture_output=True,
        timeout=90,
    )
    combined = result.stdout.decode() + result.stderr.decode()
    m = re.search(r">>>T_S<<<(.+?)>>>T_E<<<", combined, re.DOTALL)
    if not m:
        raise RuntimeError(
            "Could not extract PAT from artisan tinker output.\n"
            f"stdout: {result.stdout.decode()[:800]}\n"
            f"stderr: {result.stderr.decode()[:800]}"
        )
    return m.group(1).strip()


@pytest.fixture(scope="session")
def firefly_env():
    """Yield (base_url, api_token) for a live Firefly III instance."""
    ext_url = os.environ.get("FIREFLY_TEST_URL", "").rstrip("/")
    ext_tok = os.environ.get("FIREFLY_TEST_TOKEN", "")
    if ext_url and ext_tok:
        yield ext_url, ext_tok
        return

    project = f"ffinttest{uuid.uuid4().hex[:8]}"
    try:
        subprocess.run(
            ["docker", "compose", "-f", _COMPOSE_FILE, "-p", project, "up", "-d"],
            check=True,
        )
        base_url = f"http://localhost:{_PORT}"
        _wait_for_firefly(base_url)
        token = _bootstrap_token(_COMPOSE_FILE, project)
        yield base_url, token
    finally:
        subprocess.run(
            ["docker", "compose", "-f", _COMPOSE_FILE, "-p", project, "down", "-v"],
            check=False,
        )


@pytest.fixture(scope="session")
def ff_client(firefly_env):
    base_url, token = firefly_env
    # Firefly III API lives under /api
    api_base = base_url.rstrip("/")
    if not api_base.endswith("/api"):
        api_base = f"{api_base}/api"
    return FireflyClient(base_url=api_base, api_token=token)


# ---------------------------------------------------------------------------
# Fixture data
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def seed(ff_client):
    """Create accounts, categories, and transactions; return a dict of their IDs."""
    from firefly_iii_client.api import AccountsApi, TransactionsApi
    from firefly_iii_client.models import (
        AccountStore,
        ShortAccountTypeProperty,
        TransactionSplitStore,
        TransactionStore,
        TransactionTypeProperty,
    )

    acc_api = AccountsApi(ff_client.api_client)
    tx_api = TransactionsApi(ff_client.api_client)

    # --- accounts ---
    checking = acc_api.store_account(
        AccountStore(
            name="IT Checking",
            type=ShortAccountTypeProperty("asset"),
            currency_code="EUR",
        )
    ).data

    acc_api.store_account(
        AccountStore(
            name="IT Employer",
            type=ShortAccountTypeProperty("revenue"),
            currency_code="EUR",
        )
    )

    acc_api.store_account(
        AccountStore(
            name="IT Supermarket",
            type=ShortAccountTypeProperty("expense"),
            currency_code="EUR",
        )
    )

    # --- transactions ---
    # Withdrawal: Groceries — has category + tags (for tag/category/insight tests)
    tx_groceries = tx_api.store_transaction(
        TransactionStore(
            transactions=[
                TransactionSplitStore(
                    type=TransactionTypeProperty("withdrawal"),
                    var_date=datetime.datetime(2024, 1, 15),
                    amount="50.00",
                    description="IT Groceries run",
                    source_id=str(checking.id),
                    destination_name="IT Supermarket",
                    category_name="IT Food",
                    tags=["integration", "groceries"],
                    currency_code="EUR",
                )
            ]
        )
    ).data

    # Deposit: Salary — has category (for income insight tests)
    tx_salary = tx_api.store_transaction(
        TransactionStore(
            transactions=[
                TransactionSplitStore(
                    type=TransactionTypeProperty("deposit"),
                    var_date=datetime.datetime(2024, 1, 1),
                    amount="3000.00",
                    description="IT Monthly salary",
                    source_name="IT Employer",
                    destination_id=str(checking.id),
                    category_name="IT Income",
                    currency_code="EUR",
                )
            ]
        )
    ).data

    # Withdrawal: Transport — no category/tags initially (used by update tests)
    tx_transport = tx_api.store_transaction(
        TransactionStore(
            transactions=[
                TransactionSplitStore(
                    type=TransactionTypeProperty("withdrawal"),
                    var_date=datetime.datetime(2024, 1, 10),
                    amount="25.00",
                    description="IT Bus pass",
                    source_id=str(checking.id),
                    destination_name="IT Supermarket",
                    currency_code="EUR",
                )
            ]
        )
    ).data

    return {
        "checking_id": str(checking.id),
        "tx_groceries_id": str(tx_groceries.id),
        "tx_salary_id": str(tx_salary.id),
        "tx_transport_id": str(tx_transport.id),
    }


# ---------------------------------------------------------------------------
# Read-only tool tests
# ---------------------------------------------------------------------------

def test_list_transactions(ff_client, seed):
    result = dispatch(ff_client, "list_transactions", {"limit": 50})
    assert "transactions" in result
    assert len(result["transactions"]) >= 3


def test_get_transactions_by_date_range(ff_client, seed):
    result = dispatch(ff_client, "get_transactions_by_date_range", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "transactions" in result
    descriptions = [
        split["description"]
        for tx in result["transactions"]
        for split in tx.get("attributes", {}).get("transactions", [])
    ]
    assert any("IT" in d for d in descriptions)


def test_get_transactions_by_date_range_excludes_other_months(ff_client, seed):
    result = dispatch(ff_client, "get_transactions_by_date_range", {
        "start_date": "2024-02-01",
        "end_date": "2024-02-29",
    })
    assert "transactions" in result
    assert result["transactions"] == []


def test_search_transactions(ff_client, seed):
    result = dispatch(ff_client, "search_transactions", {"query": "IT Groceries"})
    assert "transactions" in result
    assert len(result["transactions"]) >= 1
    descriptions = [
        split["description"]
        for tx in result["transactions"]
        for split in tx.get("attributes", {}).get("transactions", [])
    ]
    assert any("IT Groceries" in d for d in descriptions)


def test_list_accounts(ff_client, seed):
    result = dispatch(ff_client, "list_accounts", {})
    assert "accounts" in result
    names = [a.get("attributes", {}).get("name", "") for a in result["accounts"]]
    assert "IT Checking" in names


def test_list_accounts_type_filter(ff_client, seed):
    result = dispatch(ff_client, "list_accounts", {"account_type": "asset"})
    assert "accounts" in result
    types = [a.get("attributes", {}).get("type", "") for a in result["accounts"]]
    assert all(t == "asset" for t in types)


def test_get_expense_insights(ff_client, seed):
    result = dispatch(ff_client, "get_expense_insights", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "insights" in result
    names = [i.get("name", "") for i in result["insights"]]
    assert "IT Food" in names


def test_get_income_insights(ff_client, seed):
    result = dispatch(ff_client, "get_income_insights", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "insights" in result
    names = [i.get("name", "") for i in result["insights"]]
    assert "IT Income" in names


def test_list_categories(ff_client, seed):
    result = dispatch(ff_client, "list_categories", {})
    assert "categories" in result
    names = [c.get("attributes", {}).get("name", "") for c in result["categories"]]
    assert "IT Food" in names
    assert "IT Income" in names


def test_list_tags(ff_client, seed):
    result = dispatch(ff_client, "list_tags", {})
    assert "tags" in result
    tag_names = [t.get("attributes", {}).get("tag", "") for t in result["tags"]]
    assert "integration" in tag_names
    assert "groceries" in tag_names


def test_calculate_net(ff_client, seed):
    result = dispatch(ff_client, "calculate_net", {
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
    })
    assert "error" not in result
    assert "net" in result
    # Income (3000) > expenses (50 groceries; transport has no category so not in insights)
    assert float(result["total_income"]) > 0
    assert float(result["total_expenses"]) > 0
    assert float(result["net"]) > 0


def test_compare_periods(ff_client, seed):
    result = dispatch(ff_client, "compare_periods", {
        "period_a_start": "2024-01-01",
        "period_a_end": "2024-01-31",
        "period_b_start": "2024-02-01",
        "period_b_end": "2024-02-29",
    })
    assert "error" not in result
    assert "period_a" in result and "period_b" in result and "delta" in result
    # Period A has income; period B has none → income delta is negative
    assert float(result["period_a"]["total_income"]) > 0
    assert float(result["period_b"]["total_income"]) == 0.0


# ---------------------------------------------------------------------------
# Write tool tests (use tx_transport which starts with no tags/category)
# ---------------------------------------------------------------------------

def test_update_transaction_tags(ff_client, seed):
    result = dispatch(ff_client, "update_transaction_tags", {
        "transaction_id": seed["tx_transport_id"],
        "tags": ["transit", "monthly"],
    })
    assert "error" not in result
    # Verify the tags were persisted
    splits = result.get("attributes", {}).get("transactions", [])
    assert splits, "Expected at least one split in the response"
    assert set(splits[0].get("tags", [])) == {"transit", "monthly"}


def test_update_transaction_category(ff_client, seed):
    result = dispatch(ff_client, "update_transaction_category", {
        "transaction_id": seed["tx_transport_id"],
        "category_name": "IT Transport",
    })
    assert "error" not in result
    splits = result.get("attributes", {}).get("transactions", [])
    assert splits, "Expected at least one split in the response"
    assert splits[0].get("category_name") == "IT Transport"
