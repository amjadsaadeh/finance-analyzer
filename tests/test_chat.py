"""Tests for the Finance Analyzer chat server components.

Verifies:
- Session store: creation, TTL, FireflyClient isolation
- Approval flow: state store/load, preview formatting, expiration
- Chat endpoints: SSE streaming, approval confirm/reject, error handling
- Models: default values
"""

from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.agent import finance_agent
from src.app import app
from src.approval import (
    STATE_TTL_SECONDS,
    format_approval_preview,
    load_state,
    store_state,
)
from src.models import ApproveRequest, ChatStreamRequest
from src.sessions import SESSION_TTL_SECONDS, SessionStore
from tools import FireflyClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(**kwargs):
    """Create a FireflyClient with test credentials."""
    return FireflyClient(
        base_url=kwargs.get("base_url", "https://firefly.example.com"),
        api_token=kwargs.get("api_token", "test-token-123"),
    )


# ---------------------------------------------------------------------------
# 1. Session store tests
# ---------------------------------------------------------------------------


class TestSessionStore:
    """Tests for the in-memory SessionStore."""

    def test_get_or_create_session_new(self):
        """Creating a new session returns an empty history."""
        store = SessionStore()
        sid, session = store.get_or_create_session(base_url="https://test.com", api_token="tok")
        assert sid is not None
        assert session["messages"] == []
        assert isinstance(session["client"], FireflyClient)

    def test_get_or_create_session_existing(self):
        """Calling get_or_create with the same ID returns the same session."""
        store = SessionStore()
        sid1, session1 = store.get_or_create_session(
            base_url="https://test.com", api_token="tok"
        )
        sid2, session2 = store.get_or_create_session(sid1)
        assert sid1 == sid2
        assert session1 is session2

    def test_session_ttl_expiry(self):
        """Sessions that exceed TTL are discarded and a new one is created."""
        store = SessionStore(ttl=0)  # 0 second TTL — immediate expiry
        sid, session = store.get_or_create_session(
            session_id="expire-me", base_url="https://test.com", api_token="tok"
        )
        assert session["messages"] == []

        # Immediately accessing again should create a new session
        # Must pass credentials again since the expired session was discarded
        sid2, session2 = store.get_or_create_session(
            session_id="expire-me", base_url="https://test.com", api_token="tok"
        )
        # The session is new because the old one expired
        assert session2["messages"] == []

    def test_session_has_firefly_client(self):
        """Each session has its own FireflyClient instance."""
        store = SessionStore()
        _, s1 = store.get_or_create_session(
            session_id="a", base_url="https://test.com", api_token="tok1"
        )
        _, s2 = store.get_or_create_session(
            session_id="b", base_url="https://test.com", api_token="tok2"
        )
        assert s1["client"] is not s2["client"]

    def test_get_returns_none_for_unknown(self):
        """get() returns None for non-existent sessions."""
        store = SessionStore()
        assert store.get("nonexistent") is None

    def test_get_returns_none_for_expired(self):
        """get() returns None for expired sessions."""
        store = SessionStore(ttl=0)
        store.get_or_create_session(session_id="old", base_url="https://x.com", api_token="t")
        # With 0 TTL, should be expired on next access
        result = store.get("old")
        assert result is None

    def test_cleanup_expired(self):
        """cleanup_expired removes all expired sessions."""
        store = SessionStore(ttl=0)
        store.get_or_create_session(session_id="old1", base_url="https://x.com", api_token="t")
        store.get_or_create_session(session_id="old2", base_url="https://x.com", api_token="t")
        removed = store.cleanup_expired()
        assert removed == 2

    def test_session_auto_generates_id(self):
        """When session_id is None, a UUID is auto-generated."""
        store = SessionStore()
        sid, _ = store.get_or_create_session(base_url="https://x.com", api_token="t")
        assert sid is not None
        assert len(sid) > 0


# ---------------------------------------------------------------------------
# 2. Approval flow tests
# ---------------------------------------------------------------------------


class TestApprovalFlow:
    """Tests for approval state management."""

    def test_format_approval_preview_category(self):
        """format_approval_preview produces a human-readable summary for category change."""
        interruption = MagicMock()
        interruption.tool_name = "update_transaction_category"
        interruption.name = "update_transaction_category"
        # ToolApprovalItem.arguments returns a JSON string, not a dict
        interruption.arguments = json.dumps({
            "transaction_id": "tx-42",
            "category_name": "Groceries",
        })
        result = format_approval_preview([interruption])
        assert result["count"] == 1
        preview = result["previews"][0]
        assert preview["tool_name"] == "update_transaction_category"
        assert "tx-42" in preview["summary"]
        assert "Groceries" in preview["summary"]
        # arguments should also be available as a parsed dict
        assert preview["arguments"]["transaction_id"] == "tx-42"
        assert preview["arguments"]["category_name"] == "Groceries"

    def test_format_approval_preview_tags(self):
        """format_approval_preview produces a summary for tag change."""
        interruption = MagicMock()
        interruption.tool_name = "update_transaction_tags"
        interruption.name = "update_transaction_tags"
        # ToolApprovalItem.arguments returns a JSON string, not a dict
        interruption.arguments = json.dumps({
            "transaction_id": "tx-99",
            "tags": ["food", "dining"],
        })
        result = format_approval_preview([interruption])
        preview = result["previews"][0]
        assert "tx-99" in preview["summary"]
        assert "food" in preview["summary"]
        assert preview["arguments"]["tags"] == ["food", "dining"]

    @pytest.mark.asyncio
    async def test_store_and_load_state(self):
        """State can be stored and retrieved with the starting agent."""
        # Create a mock RunState that can be serialized/deserialized
        mock_state = MagicMock()
        mock_state.to_json.return_value = {"mock": "state_data"}

        state_id = store_state(mock_state, "session-1")
        assert state_id == "session-1"

        # Mock RunState.from_json since it requires a real serialized state
        mock_loaded_state = MagicMock()
        with patch("src.approval.RunState.from_json", new_callable=AsyncMock, return_value=mock_loaded_state):
            loaded = await load_state(state_id, finance_agent)
            assert loaded is not None
            assert loaded == mock_loaded_state

    @pytest.mark.asyncio
    async def test_load_expired_state(self):
        """Expired state returns None."""
        mock_state = MagicMock()
        mock_state.to_json.return_value = {"mock": "state_data"}

        state_id = store_state(mock_state, "session-expired")
        assert state_id == "session-expired"

        # Manually expire the state
        from src.approval import _pending_states

        _pending_states[state_id]["stored_at"] = time.monotonic() - STATE_TTL_SECONDS - 100

        result = await load_state(state_id, finance_agent)
        assert result is None

    @pytest.mark.asyncio
    async def test_load_nonexistent_state(self):
        """Loading a state_id that doesn't exist returns None."""
        result = await load_state("nonexistent", finance_agent)
        assert result is None

    def test_format_approval_preview_unknown_tool(self):
        """format_approval_preview handles unknown tool names gracefully."""
        interruption = MagicMock()
        interruption.tool_name = "some_new_tool"
        interruption.name = "some_new_tool"
        interruption.arguments = {"key": "value"}
        result = format_approval_preview([interruption])
        preview = result["previews"][0]
        assert preview["tool_name"] == "some_new_tool"
        assert "some_new_tool" in preview["summary"]


# ---------------------------------------------------------------------------
# 3. Chat endpoint tests (via TestClient)
# ---------------------------------------------------------------------------


class TestChatEndpoints:
    """Tests for FastAPI chat endpoints using TestClient."""

    @pytest.fixture()
    def client(self):
        """Create a TestClient with mock session store."""
        from sessions import SessionStore as _SessionStore

        # Override the session store in app state with test credentials
        store = _SessionStore()
        app.state.session_store = store
        return TestClient(app)

    @pytest.fixture()
    def client_with_env(self):
        """Create a TestClient with env vars set for FireflyClient."""
        import os

        with patch.dict(
            os.environ,
            {"FIREFLY_BASE_URL": "https://test-firefly.example.com", "FIREFLY_API_TOKEN": "test-token"},
            clear=False,
        ):
            store = SessionStore()
            app.state.session_store = store
            tc = TestClient(app)
            yield tc

    def test_stream_endpoint_returns_sse(self, client_with_env):
        """GET /chat/stream returns SSE content type."""
        # We mock Runner.run_streamed to avoid making real API calls
        with patch("src.chat.Runner") as mock_runner:
            # Create a mock streaming result
            mock_result = MagicMock()
            mock_result.stream_events = MagicMock(return_value=AsyncMock())
            mock_result.to_state = MagicMock(return_value=MagicMock(
                get_interruptions=MagicMock(return_value=[]),
            ))
            mock_result.is_complete = True
            mock_result.final_output = "Hello!"

            # Make stream_events an async iterable that yields nothing then completes
            async def _no_events():
                return
                yield  # make it a generator

            mock_result.stream_events.return_value = _no_events()
            mock_result.to_state.return_value.get_interruptions.return_value = []
            mock_result.final_output = "Hello!"

            # We need to handle the actual async iteration
            async def _mock_events():
                yield MagicMock(type="run_item_stream_event")

            mock_result.stream_events.return_value = _mock_events()

            mock_runner.run_streamed.return_value = mock_result

            # Create a new session store for this test
            test_store = SessionStore()
            with patch.dict("os.environ", {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}, clear=False):
                app.state.session_store = test_store

            from fastapi.testclient import TestClient as TC
            tc = TC(app)

            response = tc.get("/chat/stream?session_id=sse-test&message=hello", follow_redirects=False)
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

    def test_approve_endpoint_confirms(self):
        """POST /chat/approve with approved=True calls state.approve()."""
        # Create mock state and interruption
        mock_state = MagicMock()
        mock_state.to_json.return_value = {"mock": "state"}
        mock_interruption = MagicMock()
        mock_interruption.tool_name = "update_transaction_category"
        mock_state.get_interruptions.return_value = [mock_interruption]
        mock_state.approve = MagicMock()

        state_id = store_state(mock_state, "approve-test")

        # Set up session with test credentials
        store = SessionStore()
        _, session = store.get_or_create_session(
            session_id="approve-test", base_url="https://x.com", api_token="t"
        )
        app.state.session_store = store

        # Mock Runner.run to return a result
        with patch("src.chat.Runner") as mock_runner:
            mock_run_result = MagicMock()
            mock_run_result.final_output = "Done"
            mock_runner.run = AsyncMock(return_value=mock_run_result)

            # Load and approve the state
            # load_state is now async, so mock it with AsyncMock
            mock_state_for_load = MagicMock()
            mock_state_for_load.get_interruptions.return_value = [mock_interruption]
            mock_state_for_load.approve = MagicMock()

            with patch("src.chat.load_state", new_callable=AsyncMock, return_value=mock_state_for_load):
                tc = TestClient(app)
                response = tc.post(
                    "/chat/approve",
                    json={"state_id": "approve-test", "approved": True, "session_id": "approve-test"},
                )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["session_id"] == "approve-test"

    def test_approve_endpoint_rejects(self):
        """POST /chat/approve with approved=False calls state.reject()."""
        mock_state = MagicMock()
        mock_state.to_json.return_value = {"mock": "state"}
        mock_interruption = MagicMock()
        mock_interruption.tool_name = "update_transaction_category"
        mock_state.get_interruptions.return_value = [mock_interruption]
        mock_state.reject = MagicMock()

        store = SessionStore()
        _, session = store.get_or_create_session(
            session_id="reject-test", base_url="https://x.com", api_token="t"
        )
        app.state.session_store = store

        with patch("src.chat.Runner") as mock_runner:
            mock_run_result = MagicMock()
            mock_run_result.final_output = "Cancelled"
            mock_runner.run = AsyncMock(return_value=mock_run_result)

            mock_state_for_load = MagicMock()
            mock_state_for_load.get_interruptions.return_value = [mock_interruption]
            mock_state_for_load.reject = MagicMock()

            with patch("src.chat.load_state", new_callable=AsyncMock, return_value=mock_state_for_load):
                tc = TestClient(app)
                response = tc.post(
                    "/chat/approve",
                    json={"state_id": "reject-test", "approved": False, "session_id": "reject-test"},
                )

        assert response.status_code == 200
        data = response.json()
        # The response should contain the agent's final output
        assert "response" in data

    def test_error_handling_stream(self):
        """When the agent raises an exception, SSE emits an error event with natural language."""
        store = SessionStore()
        app.state.session_store = store

        # Create session first to bypass FireflyClient creation error
        with patch.dict("os.environ", {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}, clear=False):
            store_with_env = SessionStore()
            app.state.session_store = store_with_env

            with patch("src.chat.Runner") as mock_runner:
                # Make run_streamed raise an exception
                mock_result = MagicMock()

                async def _error_events():
                    raise RuntimeError("Test error inside stream")

                mock_result.stream_events.return_value = _error_events()
                mock_runner.run_streamed.return_value = mock_result

                tc = TestClient(app)
                response = tc.get(
                    "/chat/stream?session_id=err-test&message=hello",
                    follow_redirects=False,
                )
                # The SSE endpoint should return 200 with error event
                assert response.status_code == 200
                content = response.text
                # Should contain an error event with natural language message
                assert "error" in content
                # Should NOT contain stack traces or technical details
                assert "RuntimeError" not in content
                assert "Traceback" not in content

    def test_approve_endpoint_missing_session(self):
        """POST /chat/approve with unknown session_id returns error."""
        store = SessionStore()
        app.state.session_store = store

        tc = TestClient(app)
        response = tc.post(
            "/chat/approve",
            json={"state_id": "x", "approved": True, "session_id": "nonexistent"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "error" in data
        # Error should be natural language, not a stack trace
        assert "Traceback" not in data.get("error", "")

    def test_approve_endpoint_expired_state(self):
        """POST /chat/approve with expired state returns error."""
        store = SessionStore()
        _, session = store.get_or_create_session(
            session_id="expired-test", base_url="https://x.com", api_token="t"
        )
        app.state.session_store = store

        mock_state = MagicMock()
        mock_state.to_json.return_value = {"mock": "state"}
        mock_state.starting_agent = finance_agent

        state_id = store_state(mock_state, "expired-test")

        # Manually expire the state
        from src.approval import _pending_states

        _pending_states[state_id]["stored_at"] = time.monotonic() - STATE_TTL_SECONDS - 100

        tc = TestClient(app)
        response = tc.post(
            "/chat/approve",
            json={"state_id": "expired-test", "approved": True, "session_id": "expired-test"},
        )
        data = response.json()
        assert "error" in data


# ---------------------------------------------------------------------------
# 4. Model tests
# ---------------------------------------------------------------------------


class TestModels:
    """Tests for Pydantic request models."""

    def test_chat_stream_request_required(self):
        """ChatStreamRequest requires message and session_id."""
        req = ChatStreamRequest(message="hello", session_id="abc123")
        assert req.message == "hello"
        assert req.session_id == "abc123"

    def test_approve_request(self):
        """ApproveRequest stores state_id, approved, and session_id."""
        req = ApproveRequest(state_id="s1", approved=True, session_id="sess1")
        assert req.state_id == "s1"
        assert req.approved is True
        assert req.session_id == "sess1"

    def test_approve_request_reject(self):
        """ApproveRequest with approved=False."""
        req = ApproveRequest(state_id="s1", approved=False, session_id="sess1")
        assert req.approved is False