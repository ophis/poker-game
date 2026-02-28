"""GameState dataclass, GamePhase, and GameVariant enums."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

from app.core.card import Card


class GamePhase(Enum):
    WAITING = "waiting"
    STARTING = "starting"
    PREFLOP = "preflop"
    FLOP = "flop"
    TURN = "turn"
    RIVER = "river"
    SHOWDOWN = "showdown"
    HAND_OVER = "hand_over"


class GameVariant(Enum):
    NO_LIMIT = "no_limit"
    FIXED_LIMIT = "fixed_limit"


@dataclass
class PlayerState:
    player_id: str
    name: str
    chips: int
    hole_cards: List[Card] = field(default_factory=list)
    bet: int = 0           # chips bet in current street
    total_bet: int = 0     # total chips in pot this hand
    is_folded: bool = False
    is_all_in: bool = False
    is_sitting_out: bool = False
    is_bot: bool = False
    seat: int = 0          # 0-based seat index


@dataclass
class GameState:
    game_id: str
    variant: GameVariant
    small_blind: int
    big_blind: int
    max_players: int
    phase: GamePhase = GamePhase.WAITING
    players: List[PlayerState] = field(default_factory=list)
    community_cards: List[Card] = field(default_factory=list)
    pot: int = 0
    side_pots: List[Dict[str, Any]] = field(default_factory=list)
    dealer_index: int = 0          # index into players list
    current_player_index: int = 0  # index of active player
    hand_number: int = 0
    last_aggressor_index: int = -1  # who last bet/raised
    min_buy_in: int = 0
    max_buy_in: int = 0

    @property
    def active_players(self) -> List[PlayerState]:
        """Players still in the hand (not folded, not sitting out)."""
        return [p for p in self.players if not p.is_folded and not p.is_sitting_out]

    @property
    def seated_players(self) -> List[PlayerState]:
        """All players seated (not sitting out)."""
        return [p for p in self.players if not p.is_sitting_out]

    @property
    def current_player(self) -> Optional[PlayerState]:
        if 0 <= self.current_player_index < len(self.players):
            return self.players[self.current_player_index]
        return None

    def get_player(self, player_id: str) -> Optional[PlayerState]:
        for p in self.players:
            if p.player_id == player_id:
                return p
        return None

    def player_index(self, player_id: str) -> int:
        for i, p in enumerate(self.players):
            if p.player_id == player_id:
                return i
        return -1
