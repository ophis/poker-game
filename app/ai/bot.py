"""BotPlayer — wires HandStrengthEstimator + StrategyEngine together."""
from __future__ import annotations
from typing import Tuple

from app.ai.hand_strength import HandStrengthEstimator
from app.ai.strategy import StrategyEngine
from app.game.betting import BettingAction, ValidActions
from app.game.game_state import GameState, PlayerState


class BotPlayer:
    """
    Stateless bot decision-maker.

    Called from PokerGame._schedule_bot_action() with the current
    game state, player state, valid actions, and difficulty.
    """

    def __init__(self, player_id: str) -> None:
        self.player_id = player_id
        self._estimator = HandStrengthEstimator()
        self._strategy = StrategyEngine()

    def decide(
        self,
        state: GameState,
        player: PlayerState,
        valid: ValidActions,
        difficulty: str = "medium",
    ) -> Tuple[BettingAction, int]:
        """
        Return (action, amount).
        amount is meaningful only for RAISE actions (total bet size).
        """
        if not player.hole_cards:
            # No cards — shouldn't happen, but fold safely
            return BettingAction.FOLD, 0

        # Count opponents who haven't folded
        num_opponents = sum(
            1 for p in state.players
            if p.player_id != self.player_id
            and not p.is_folded
            and not p.is_sitting_out
        )
        num_opponents = max(1, num_opponents)

        equity = self._estimator.estimate(
            hole_cards=player.hole_cards,
            community_cards=state.community_cards,
            num_opponents=num_opponents,
            difficulty=difficulty,
        )

        action, amount = self._strategy.decide(
            state=state,
            player=player,
            valid=valid,
            equity=equity,
            difficulty=difficulty,
        )

        # Final safety: never raise more than stack
        if action == BettingAction.RAISE:
            max_bet = player.chips + player.bet
            if amount > max_bet:
                amount = max_bet
            if amount <= valid.call_amount:
                action = BettingAction.CALL
                amount = valid.call_amount

        return action, amount
