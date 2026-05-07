"""Pydantic models for the Finance Analyzer chat API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Request body for POST /chat (non-streaming chat)."""

    message: str = Field(..., description="User message to send to the agent")
    session_id: str | None = Field(
        None, description="Existing session ID; omitted to start a new session"
    )


class ChatStreamRequest(BaseModel):
    """Query parameters for GET /chat/stream (SSE streaming)."""

    message: str = Field(..., description="User message to send to the agent")
    session_id: str = Field(..., description="Session ID for conversation context")


class ApproveRequest(BaseModel):
    """Request body for POST /chat/approve (confirm or reject a pending write)."""

    state_id: str = Field(..., description="ID of the stored agent state to resume")
    approved: bool = Field(..., description="True to confirm the write, False to reject")
    session_id: str = Field(..., description="Session ID that owns the pending state")