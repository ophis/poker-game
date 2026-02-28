"""In-memory PokerGame store."""
from __future__ import annotations
import uuid
from typing import Dict, List, Optional

from app.game.game import PokerGame
from app.game.game_state import GameVariant


class GameManager:
    def __init__(self) -> None:
        self._games: Dict[str, PokerGame] = {}

    def create_game(
        self,
        variant: GameVariant,
        small_blind: int,
        big_blind: int,
        max_players: int = 9,
        min_buy_in: Optional[int] = None,
        max_buy_in: Optional[int] = None,
    ) -> PokerGame:
        game_id = str(uuid.uuid4())[:8]
        game = PokerGame(
            game_id=game_id,
            variant=variant,
            small_blind=small_blind,
            big_blind=big_blind,
            max_players=max_players,
            min_buy_in=min_buy_in,
            max_buy_in=max_buy_in,
        )
        self._games[game_id] = game
        return game

    def get_game(self, game_id: str) -> Optional[PokerGame]:
        return self._games.get(game_id)

    def list_games(self) -> List[dict]:
        result = []
        for gid, game in self._games.items():
            state = game.state
            result.append({
                "game_id": gid,
                "variant": state.variant.value,
                "phase": state.phase.value,
                "players": len(state.players),
                "max_players": state.max_players,
                "small_blind": state.small_blind,
                "big_blind": state.big_blind,
                "hand_number": state.hand_number,
            })
        return result

    def delete_game(self, game_id: str) -> bool:
        if game_id in self._games:
            del self._games[game_id]
            return True
        return False


# Global singleton
game_manager = GameManager()
