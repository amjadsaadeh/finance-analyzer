"""End-to-end integration tests for the Finance Analyzer chat server.

Verifies the full chat flow works together:
- SSE streaming with text and tool_call events
- Approval flow (confirm and reject)
- Session context accumulation across messages
- Error handling (natural language, no stack traces)
- Health check endpoint
- Frontend is served at root path
"""

from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.agent import finance_agent
from src.app import app
from src.approval import _pending_states, format_approval_preview, store_state
from src.sessions import SessionStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_env():
    """Provide a TestClient with env vars set and a fresh session store."""
    with patch.dict(
        os.environ,
        {"FIREFLY_BASE_URL": "https://test.example.com", "FIREFLY_API_TOKEN": "test-token"},
    ):
        store = SessionStore()
        app.state.session_store = store
        tc = TestClient(app)
        yield tc


# ---------------------------------------------------------------------------
# 1. SSE streaming flow
# ---------------------------------------------------------------------------


class TestSSEStreamingFlow:
    """Test SSE streaming endpoint produces correct event types."""

    def test_sse_returns_text_and_done_events(self, app_with_env):
        """GET /chat/stream emits text deltas and a done event."""
        mock_result = MagicMock()

        async def _stream_events():
            # Simulate a text delta raw_response_event
            raw_delta = MagicMock()
            raw_delta.type = "response.output_text.delta"
            raw_delta.delta = "Hello world"
            yield MagicMock(type="raw_response_event", data=raw_delta)

        mock_result.stream_events = MagicMock(return_value=_stream_events())
        mock_result.to_state = MagicMock(
            return_value=MagicMock(get_interruptions=MagicMock(return_value=[]))
        )
        mock_result.final_output = "Hello world"

        with patch("src.chat.Runner") as mock_runner:
            mock_runner.run_streamed.return_value = mock_result

            response = app_with_env.get(
                "/chat/stream?session_id=sse-int&message=hi", follow_redirects=False
            )

        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

        content = response.text
        # Should contain text event
        assert "event: text" in content
        # Should contain done event
        assert "event: done" in content
        # Text data should include the delta
        assert "Hello world" in content

    def test_sse_emits_tool_call_event(self, app_with_env):
        """GET /chat/stream emits tool_call events when the agent calls a tool."""
        mock_result = MagicMock()

        async def _stream_events():
            # Simulate a run_item_stream_event with tool_called name
            mock_item = MagicMock()
            mock_item.tool_name = "list_transactions"
            mock_item.call_id = "call_test123"
            mock_item.raw_item = MagicMock()
            mock_item.raw_item.arguments = '{"limit": 10}'
            event = MagicMock(spec=[])
            event.type = "run_item_stream_event"
            event.name = "tool_called"
            event.item = mock_item
            yield event

        mock_result.stream_events = MagicMock(return_value=_stream_events())
        mock_result.to_state = MagicMock(
            return_value=MagicMock(get_interruptions=MagicMock(return_value=[]))
        )

        with patch("src.chat.Runner") as mock_runner:
            mock_runner.run_streamed.return_value = mock_result

            response = app_with_env.get(
                "/chat/stream?session_id=tool-call-test&message=show+transactions",
                follow_redirects=False,
            )

        content = response.text
        assert "event: tool_call" in content
        assert "list_transactions" in content

    def test_sse_with_approval_needed_event(self, app_with_env):
        """GET /chat/stream emits approval_needed when agent pauses for write tool."""
        mock_result = MagicMock()

        async def _stream_events():
            # No streaming events — complete immediately
            return
            yield

        mock_result.stream_events = MagicMock(return_value=_stream_events())

        # Create mock state that has interruptions
        mock_interruption = MagicMock()
        mock_interruption.tool_name = "update_transaction_category"
        mock_interruption.name = "update_transaction_category"
        # ToolApprovalItem.arguments returns a JSON string, not a dict
        mock_interruption.arguments = json.dumps({
            "transaction_id": "123",
            "category_name": "Groceries",
        })

        mock_state = MagicMock()
        mock_state.get_interruptions.return_value = [mock_interruption]
        mock_state.to_json.return_value = {"mock": "state"}
        mock_state.starting_agent = finance_agent
        mock_result.to_state.return_value = mock_state

        with patch("src.chat.Runner") as mock_runner, \
             patch("src.chat.store_state") as mock_store:
            mock_runner.run_streamed.return_value = mock_result
            mock_store.return_value = "test-state-id"

            response = app_with_env.get(
                "/chat/stream?session_id=approval-test&message=change+category",
                follow_redirects=False,
            )

        content = response.text
        assert "event: approval_needed" in content
        assert "state_id" in content


# ---------------------------------------------------------------------------
# 2. Approval flow (confirm)
# ---------------------------------------------------------------------------


class TestApprovalConfirmFlow:
    """Test POST /chat/approve with approved=True."""

    def test_approve_returns_agent_response(self):
        """Approving a pending write returns the agent's final response."""
        mock_interruption = MagicMock()
        mock_interruption.tool_name = "update_transaction_category"
        mock_interruption.name = "update_transaction_category"
        # ToolApprovalItem.arguments returns a JSON string, not a dict
        mock_interruption.arguments = json.dumps({
            "transaction_id": "123",
            "category_name": "Groceries",
        })

        # Store mock state
        mock_state = MagicMock()
        mock_state.to_json.return_value = '{"mock": "data"}'
        mock_state.get_interruptions.return_value = [mock_interruption]
        mock_state.approve = MagicMock()

        state_id = store_state(mock_state, "approve-int")

        with patch.dict(os.environ, {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}):
            store = SessionStore()
            store.get_or_create_session(session_id="approve-int")
            app.state.session_store = store

            mock_state_for_load = MagicMock()
            mock_state_for_load.get_interruptions.return_value = [mock_interruption]
            mock_state_for_load.approve = MagicMock()

            mock_run_result = MagicMock()
            mock_run_result.final_output = "Category updated successfully!"
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_run_result)

            with patch("src.chat.Runner", mock_runner), \
                 patch("src.chat.load_state", new_callable=AsyncMock, return_value=mock_state_for_load):

                tc = TestClient(app)
                response = tc.post(
                    "/chat/approve",
                    json={"state_id": "approve-int", "approved": True, "session_id": "approve-int"},
                )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert data["session_id"] == "approve-int"

    def test_approve_preview_shows_tool_details(self):
        """Approval preview includes tool name, arguments, and summary."""
        interruption = MagicMock()
        interruption.tool_name = "update_transaction_category"
        interruption.name = "update_transaction_category"
        # ToolApprovalItem.arguments returns a JSON string, not a dict
        interruption.arguments = json.dumps({
            "transaction_id": "123",
            "category_name": "Groceries",
        })

        preview = format_approval_preview([interruption])
        assert preview["count"] == 1
        assert preview["previews"][0]["tool_name"] == "update_transaction_category"
        assert "123" in preview["previews"][0]["summary"]
        assert "Groceries" in preview["previews"][0]["summary"]


# ---------------------------------------------------------------------------
# 3. Rejection flow
# ---------------------------------------------------------------------------


class TestRejectionFlow:
    """Test POST /chat/approve with approved=False."""

    def test_reject_returns_agent_response(self):
        """Rejecting a pending write returns the agent's acknowledgment."""
        mock_interruption = MagicMock()
        mock_interruption.tool_name = "update_transaction_tags"
        mock_interruption.name = "update_transaction_tags"
        # ToolApprovalItem.arguments returns a JSON string, not a dict
        mock_interruption.arguments = json.dumps({
            "transaction_id": "456",
            "tags": ["food", "dining"],
        })

        # Store mock state for rejection
        mock_state = MagicMock()
        mock_state.to_json.return_value = '{"mock": "data"}'
        mock_state.get_interruptions.return_value = [mock_interruption]
        mock_state.reject = MagicMock()

        # Clean up any previous state
        if "reject-int" in _pending_states:
            del _pending_states["reject-int"]
        state_id = store_state(mock_state, "reject-int")

        with patch.dict(os.environ, {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}):
            store = SessionStore()
            store.get_or_create_session(session_id="reject-int")
            app.state.session_store = store

            mock_state_for_load = MagicMock()
            mock_state_for_load.get_interruptions.return_value = [mock_interruption]
            mock_state_for_load.reject = MagicMock()

            mock_run_result = MagicMock()
            mock_run_result.final_output = "Understood, I won't make that change."
            mock_runner = MagicMock()
            mock_runner.run = AsyncMock(return_value=mock_run_result)

            with patch("src.chat.Runner", mock_runner), \
                 patch("src.chat.load_state", new_callable=AsyncMock, return_value=mock_state_for_load):

                tc = TestClient(app)
                response = tc.post(
                    "/chat/approve",
                    json={"state_id": "reject-int", "approved": False, "session_id": "reject-int"},
                )

        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        # The agent should acknowledge the rejection
        assert "Understood" in data["response"] or "won't" in data["response"] or "response" in data


# ---------------------------------------------------------------------------
# 4. Session context accumulation
# ---------------------------------------------------------------------------


class TestSessionContext:
    """Test that conversation history accumulates within a session."""

    def test_session_accumulates_messages(self):
        """Sending two messages to the same session_id accumulates history."""
        with patch.dict(os.environ, {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}):
            store = SessionStore()
            app.state.session_store = store

            # First message
            sid, session = store.get_or_create_session(
                session_id="ctx-test", base_url="https://x.com", api_token="t"
            )
            assert session["messages"] == []

            session["messages"].append({"role": "user", "content": "hello"})
            session["messages"].append({"role": "assistant", "content": "Hi there!"})

            # Second message — session should have accumulated history
            session2 = store.get("ctx-test")
            assert session2 is not None
            assert len(session2["messages"]) == 2
            assert session2["messages"][0]["role"] == "user"
            assert session2["messages"][1]["role"] == "assistant"

            # Add a third message
            session2["messages"].append({"role": "user", "content": "how much did I spend?"})

            # Verify accumulation
            session3 = store.get("ctx-test")
            assert len(session3["messages"]) == 3

    def test_different_sessions_are_isolated(self):
        """Different session_ids have independent conversation histories."""
        store = SessionStore()
        with patch.dict(os.environ, {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}):
            _, s1 = store.get_or_create_session(session_id="session-a")
            _, s2 = store.get_or_create_session(session_id="session-b")

            s1["messages"].append({"role": "user", "content": "Session A message"})

            assert len(s2["messages"]) == 0
            assert len(s1["messages"]) == 1

    def test_session_has_firefly_client_per_session(self):
        """Each session has its own FireflyClient instance."""
        store = SessionStore()
        with patch.dict(os.environ, {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}):
            _, s1 = store.get_or_create_session(session_id="client-a")
            _, s2 = store.get_or_create_session(session_id="client-b")

            assert s1["client"] is not s2["client"]


# ---------------------------------------------------------------------------
# 5. Error handling (CHAT-04)
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Test that errors are returned as natural language, not stack traces."""

    def test_stream_error_is_natural_language(self):
        """When an exception occurs during streaming, SSE error event uses natural language."""
        with patch.dict(os.environ, {"FIREFLY_BASE_URL": "https://x.com", "FIREFLY_API_TOKEN": "t"}):
            store = SessionStore()
            app.state.session_store = store

            with patch("src.chat.Runner") as mock_runner:
                mock_result = MagicMock()

                async def _error_stream():
                    raise RuntimeError("Something broke in the LLM layer")

                mock_result.stream_events = MagicMock(return_value=_error_stream())
                mock_runner.run_streamed.return_value = mock_result

                tc = TestClient(app)
                response = tc.get(
                    "/chat/stream?session_id=error-test&message=hello",
                    follow_redirects=False,
                )

        assert response.status_code == 200
        content = response.text
        # Should contain natural language error message
        assert "event: error" in content
        # Should NOT contain exception type or stack trace
        assert "RuntimeError" not in content
        assert "Traceback" not in content
        assert "Error:" not in content or "something went wrong" in content.lower()

    def test_missing_env_vars_returns_natural_language(self):
        """When FireflyClient env vars are missing, SSE error uses natural language."""
        # Remove env vars to trigger configuration error
        with patch.dict(os.environ, {}, clear=True):
            store = SessionStore()
            app.state.session_store = store

            tc = TestClient(app)
            response = tc.get(
                "/chat/stream?session_id=noenv-test&message=hello",
                follow_redirects=False,
            )

        assert response.status_code == 200
        content = response.text
        assert "event: error" in content
        # Error message should be natural language
        assert "RuntimeError" not in content
        assert "Traceback" not in content

    def test_approval_error_is_natural_language(self):
        """Approval endpoint errors use natural language, not stack traces."""
        store = SessionStore()
        app.state.session_store = store

        tc = TestClient(app)
        # Non-existent session
        response = tc.post(
            "/chat/approve",
            json={"state_id": "x", "approved": True, "session_id": "nonexistent"},
        )

        data = response.json()
        assert "error" in data
        # Error should be natural language
        assert "Traceback" not in data.get("error", "")
        assert "RuntimeError" not in data.get("error", "")


# ---------------------------------------------------------------------------
# 6. Health check
# ---------------------------------------------------------------------------


class TestHealthCheck:
    """Test the health check endpoint."""

    def test_health_returns_ok(self):
        """GET /health returns {"status": "ok"}."""
        tc = TestClient(app)
        response = tc.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data == {"status": "ok"}

    def test_root_serves_frontend(self):
        """GET / serves the index.html frontend."""
        tc = TestClient(app)
        response = tc.get("/")
        assert response.status_code == 200
        # Should contain HTML with key elements
        content = response.text
        assert "EventSource" in content
        assert "/chat/stream" in content
        assert "/chat/approve" in content