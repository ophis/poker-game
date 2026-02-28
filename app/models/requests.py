"""Pydantic request models for REST endpoints."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class CreateGameRequest(BaseModel):
    variant: str = Field(default="no_limit", pattern="^(no_limit|fixed_limit)$")
    small_blind: int = Field(default=10, ge=1)
    big_blind: int = Field(default=20, ge=2)
    max_players: int = Field(default=6, ge=2, le=9)
    min_buy_in: Optional[int] = None
    max_buy_in: Optional[int] = None
    num_bots: int = Field(default=0, ge=0, le=8)
    bot_difficulty: str = Field(default="medium", pattern="^(easy|medium|hard)$")
    bot_stack: int = Field(default=1000, ge=1)


class JoinGameRequest(BaseModel):
    player_name: str = Field(min_length=1, max_length=30)
    buy_in: int = Field(ge=1)
