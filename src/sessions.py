"""In-memory session store with TTL cleanup.

Each session holds:
- messages: conversation history (list of message dicts)
- client: a FireflyClient instance (not shared across sessions — see Research Pitfall 4)
- created_at: timestamp for TTL
- pending_state: serialized RunState awaiting user approval, or None
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from tools import FireflyClient

# ---------------------------------------------------------------------------
# Session TTL
# ---------------------------------------------------------------------------

SESSION_TTL_SECONDS = 30 * 60  # 30 minutes


class SessionStore:
    """Thread-safe in-memory session store with TTL cleanup.

    Each session owns its own FireflyClient instance so concurrent
    requests don't share an ApiClient (which is not documented as
    thread-safe).
    """

    def __init__(self, ttl: int = SESSION_TTL_SECONDS) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._ttl = ttl

    # -- public API -----------------------------------------------------------

    def get_or_create_session(
        self,
        session_id: str | None = None,
        base_url: str | None = None,
        api_token: str | None = None,
    ) -> tuple[str, dict[str, Any]]:
        """Return an existing session or create a new one.

        If *session_id* is None, a UUID4 is generated.  Expired sessions
        are discarded and a fresh one is created in their place.

        Returns (session_id, session_dict).
        """
        if session_id is None:
            session_id = uuid.uuid4().hex

        now = time.monotonic()

        # Expired? Start fresh with the same ID
        existing = self._sessions.get(session_id)
        if existing is not None:
            age = now - existing.get("_accessed_at", existing["created_at"])
            if age > self._ttl:
                self._sessions.pop(session_id, None)
                self._locks.pop(session_id, None)
            else:
                existing["_accessed_at"] = now
                return session_id, existing

        # Create new session
        client = FireflyClient(base_url=base_url, api_token=api_token)
        session: dict[str, Any] = {
            "messages": [],
            "client": client,
            "created_at": time.monotonic(),
            "_accessed_at": time.monotonic(),
            "pending_state": None,
        }
        self._sessions[session_id] = session
        self._locks[session_id] = asyncio.Lock()
        return session_id, session

    def get(self, session_id: str) -> dict[str, Any] | None:
        """Return session dict by ID, or None if not found or expired."""
        session = self._sessions.get(session_id)
        if session is None:
            return None
        now = time.monotonic()
        age = now - session.get("_accessed_at", session["created_at"])
        if age > self._ttl:
            self._sessions.pop(session_id, None)
            self._locks.pop(session_id, None)
            return None
        session["_accessed_at"] = now
        return session

    def get_lock(self, session_id: str) -> asyncio.Lock:
        """Return the asyncio.Lock for a session (creates one if missing)."""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def cleanup_expired(self) -> int:
        """Remove all expired sessions.  Returns the number removed."""
        now = time.monotonic()
        expired = [
            sid
            for sid, s in self._sessions.items()
            if now - s.get("_accessed_at", s["created_at"]) > self._ttl
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._locks.pop(sid, None)
        return len(expired)