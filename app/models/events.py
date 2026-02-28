"""Pydantic models for WebSocket events."""
from __future__ import annotations
from typing import Any, Dict, Optional
from pydantic import BaseModel


class ClientAction(BaseModel):
    """Client → Server: player action."""
    type: str  # "action" | "chat"
    payload: Dict[str, Any]


class ActionPayload(BaseModel):
    action: str  # "fold" | "check" | "call" | "raise" | "all_in"
    amount: Optional[int] = 0


class ChatPayload(BaseModel):
    message: str


class ServerEvent(BaseModel):
    """Server → Client event envelope."""
    type: str
    payload: Dict[str, Any]
