"""
Strategy engine for AI bots.

Easy:    mostly fold weak hands, call with medium, rarely raise
Medium:  pot-odds aware, raises good hands
Hard:    adds position awareness, bluffing (~15% frequency)
"""
from __future__ import annotations
import random
from typing import Tuple

from app.game.betting import BettingAction, ValidActions
from app.game.game_state import GameState, PlayerState


class StrategyEngine:
    """Decides the bot action given equity and game context."""

    def decide(
        self,
        state: GameState,
        player: PlayerState,
        valid: ValidActions,
        equity: float,
        difficulty: str = "medium",
    ) -> Tuple[BettingAction, int]:
        """
        Return (action, amount) where amount is the total bet for raises.
        """
        if difficulty == "easy":
            return self._easy(state, player, valid, equity)
        elif difficulty == "hard":
            return self._hard(state, player, valid, equity)
        else:
            return self._medium(state, player, valid, equity)

    # ------------------------------------------------------------------
    # Easy bot: straightforward, rarely raises
    # ------------------------------------------------------------------

    def _easy(
        self,
        state: GameState,
        player: PlayerState,
        valid: ValidActions,
        equity: float,
    ) -> Tuple[BettingAction, int]:
        if valid.can_check:
            if equity > 0.7 and valid.can_raise and random.random() < 0.3:
                amount = self._pot_size_bet(state, 0.5, valid)
                return BettingAction.RAISE, amount
            return BettingAction.CHECK, 0

        # Need to call
        pot_odds = self._pot_odds(state, valid)
        if equity < 0.35 or (equity < pot_odds and random.random() < 0.8):
            return BettingAction.FOLD, 0
        if equity > 0.7 and valid.can_raise and random.random() < 0.2:
            amount = self._pot_size_bet(state, 0.5, valid)
            return BettingAction.RAISE, amount
        return BettingAction.CALL, valid.call_amount

    # ------------------------------------------------------------------
    # Medium bot: pot-odds aware
    # ------------------------------------------------------------------

    def _medium(
        self,
        state: GameState,
        player: PlayerState,
        valid: ValidActions,
        equity: float,
    ) -> Tuple[BettingAction, int]:
        pot_odds = self._pot_odds(state, valid)

        if valid.can_check:
            if equity > 0.65 and valid.can_raise:
                amount = self._pot_size_bet(state, 0.75, valid)
                return BettingAction.RAISE, amount
            if equity > 0.5 and valid.can_raise and random.random() < 0.3:
                amount = self._pot_size_bet(state, 0.5, valid)
                return BettingAction.RAISE, amount
            return BettingAction.CHECK, 0

        # Need to call
        if equity < pot_odds:
            return BettingAction.FOLD, 0
        if equity > 0.7 and valid.can_raise:
            amount = self._pot_size_bet(state, 1.0, valid)
            return BettingAction.RAISE, amount
        if equity > 0.55 and valid.can_raise and random.random() < 0.4:
            amount = self._pot_size_bet(state, 0.75, valid)
            return BettingAction.RAISE, amount
        return BettingAction.CALL, valid.call_amount

    # ------------------------------------------------------------------
    # Hard bot: position-aware, bluffs ~15%
    # ------------------------------------------------------------------

    def _hard(
        self,
        state: GameState,
        player: PlayerState,
        valid: ValidActions,
        equity: float,
    ) -> Tuple[BettingAction, int]:
        pot_odds = self._pot_odds(state, valid)

        # Position: is this player last to act (dealer or close)?
        in_position = self._is_in_position(state, player)

        # Bluff with 15% frequency in position when board is scary
        bluffing = in_position and random.random() < 0.15

        if valid.can_check:
            if equity > 0.6 and valid.can_raise:
                size = 0.75 if in_position else 0.6
                amount = self._pot_size_bet(state, size, valid)
                return BettingAction.RAISE, amount
            if bluffing and valid.can_raise:
                amount = self._pot_size_bet(state, 0.6, valid)
                return BettingAction.RAISE, amount
            return BettingAction.CHECK, 0

        if bluffing and valid.can_raise:
            amount = self._pot_size_bet(state, 0.75, valid)
            return BettingAction.RAISE, amount

        if equity < pot_odds and not bluffing:
            return BettingAction.FOLD, 0

        if equity > 0.75 and valid.can_raise:
            # Value raise
            size = 1.0 if in_position else 0.75
            amount = self._pot_size_bet(state, size, valid)
            return BettingAction.RAISE, amount

        if equity > 0.55 and valid.can_raise and in_position and random.random() < 0.5:
            amount = self._pot_size_bet(state, 0.6, valid)
            return BettingAction.RAISE, amount

        return BettingAction.CALL, valid.call_amount

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pot_odds(self, state: GameState, valid: ValidActions) -> float:
        """Minimum equity needed to make a call breakeven."""
        call = valid.call_amount
        if call == 0:
            return 0.0
        return call / (state.pot + call)

    def _pot_size_bet(self, state: GameState, fraction: float, valid: ValidActions) -> int:
        """Calculate a raise amount as a fraction of the pot."""
        pot = max(state.pot, 1)
        target = int(valid.call_amount + pot * fraction)
        target = max(target, valid.min_raise)
        target = min(target, valid.max_raise)
        return target

    def _is_in_position(self, state: GameState, player: PlayerState) -> bool:
        """Simple position heuristic: player acts after dealer."""
        dealer_idx = state.dealer_index
        player_idx = state.player_index(player.player_id)
        n = len(state.players)
        # Seats after dealer (modular) are "in position"
        relative = (player_idx - dealer_idx) % n
        return relative >= n // 2
