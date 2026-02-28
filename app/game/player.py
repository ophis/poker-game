"""Player dataclass — thin wrapper around PlayerState for human/bot distinction."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass
class Player:
    """Represents a player seat (persistent across hands)."""
    player_id: str
    name: str
    chips: int
    is_bot: bool = False
    bot_difficulty: Optional[str] = None   # "easy" | "medium" | "hard"
    seat: int = 0
    is_connected: bool = True

    def to_dict(self) -> dict:
        return {
            "player_id": self.player_id,
            "name": self.name,
            "chips": self.chips,
            "is_bot": self.is_bot,
            "bot_difficulty": self.bot_difficulty,
            "seat": self.seat,
            "is_connected": self.is_connected,
        }
