"""
Betting round logic for NLHE and FLHE.

BettingRound manages one complete street (preflop, flop, turn, river).
"""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from app.game.game_state import GamePhase, GameState, GameVariant, PlayerState


class BettingAction(Enum):
    FOLD = "fold"
    CHECK = "check"
    CALL = "call"
    RAISE = "raise"
    ALL_IN = "all_in"


class BettingResult(Enum):
    CONTINUE = "continue"
    ROUND_COMPLETE = "round_complete"
    ALL_FOLDED = "all_folded"


@dataclass
class ValidActions:
    can_check: bool
    call_amount: int        # 0 if can check
    min_raise: int          # minimum total bet after raise
    max_raise: int          # for NLHE: stack; for FLHE: fixed
    can_raise: bool
    player_stack: int


class BettingRound:
    """
    Manages action for one betting street.

    Args:
        state: current GameState (mutated in place)
        start_player_index: index of first player to act
        phase: current GamePhase (used for FLHE bet sizing)
    """

    # FLHE: max 4 raises per street (cap)
    FLHE_MAX_RAISES = 4

    def __init__(self, state: GameState, start_player_index: int, phase: GamePhase) -> None:
        self.state = state
        self.phase = phase
        self._current_index = start_player_index
        self._num_raises = 0
        self._last_raise_size = state.big_blind
        # highest bet on the table this street
        self._current_bet = max((p.bet for p in state.players), default=0)
        # track who acted this street (for "action complete" detection)
        self._players_acted: set[str] = set()
        # the player who last raised/bet (action circles back to them)
        self._last_aggressor: Optional[str] = None

        # For FLHE, determine street bet size
        if state.variant == GameVariant.FIXED_LIMIT:
            if phase in (GamePhase.PREFLOP, GamePhase.FLOP):
                self._fixed_bet = state.big_blind
            else:  # TURN, RIVER
                self._fixed_bet = state.big_blind * 2
        else:
            self._fixed_bet = 0

    def get_valid_actions(self, player_id: str) -> ValidActions:
        state = self.state
        player = state.get_player(player_id)
        if player is None:
            raise ValueError(f"Player {player_id} not found")

        call_amount = max(0, self._current_bet - player.bet)
        call_amount = min(call_amount, player.chips)  # cap at stack
        can_check = (call_amount == 0)

        if state.variant == GameVariant.NO_LIMIT:
            # Min raise: at least as large as last raise size
            min_raise_increment = max(self._last_raise_size, state.big_blind)
            min_raise_total = self._current_bet + min_raise_increment
            max_raise_total = player.chips + player.bet  # all-in
            can_raise = (player.chips > call_amount)
        else:
            # FLHE: fixed raise size, cap at FLHE_MAX_RAISES
            min_raise_total = self._current_bet + self._fixed_bet
            max_raise_total = min_raise_total
            can_raise = (
                self._num_raises < self.FLHE_MAX_RAISES
                and player.chips > call_amount
            )

        return ValidActions(
            can_check=can_check,
            call_amount=call_amount,
            min_raise=min_raise_total,
            max_raise=max_raise_total,
            can_raise=can_raise,
            player_stack=player.chips,
        )

    def apply_action(
        self,
        player_id: str,
        action: BettingAction,
        raise_amount: int = 0,
    ) -> BettingResult:
        """
        Apply an action from a player. Returns BettingResult.

        raise_amount: for RAISE/ALL_IN, the total bet amount (not the increment).
        """
        state = self.state
        player = state.get_player(player_id)
        if player is None:
            raise ValueError(f"Player {player_id} not found")

        valid = self.get_valid_actions(player_id)

        if action == BettingAction.FOLD:
            player.is_folded = True
            self._players_acted.add(player_id)

        elif action == BettingAction.CHECK:
            if not valid.can_check:
                raise ValueError(f"Player {player_id} cannot check (must call {valid.call_amount})")
            self._players_acted.add(player_id)

        elif action == BettingAction.CALL:
            amount = valid.call_amount
            is_all_in = (amount >= player.chips)
            actual_amount = min(amount, player.chips)
            player.chips -= actual_amount
            player.bet += actual_amount
            player.total_bet += actual_amount
            state.pot += actual_amount
            if player.chips == 0:
                player.is_all_in = True
            self._players_acted.add(player_id)

        elif action in (BettingAction.RAISE, BettingAction.ALL_IN):
            if not valid.can_raise and action == BettingAction.RAISE:
                raise ValueError(f"Player {player_id} cannot raise")

            if action == BettingAction.ALL_IN:
                total_bet = player.chips + player.bet  # go all-in
            else:
                if state.variant == GameVariant.FIXED_LIMIT:
                    total_bet = self._current_bet + self._fixed_bet
                else:
                    total_bet = raise_amount
                # Enforce minimum
                total_bet = max(total_bet, valid.min_raise)
                # Cap at all-in
                total_bet = min(total_bet, player.chips + player.bet)

            raise_increment = total_bet - self._current_bet
            chips_to_add = total_bet - player.bet
            chips_to_add = min(chips_to_add, player.chips)

            player.chips -= chips_to_add
            player.bet += chips_to_add
            player.total_bet += chips_to_add
            state.pot += chips_to_add

            if player.chips == 0:
                player.is_all_in = True

            # Update table state
            self._last_raise_size = raise_increment
            self._current_bet = player.bet
            self._num_raises += 1
            self._last_aggressor = player_id
            # Others need to act again
            self._players_acted = {player_id}

        else:
            raise ValueError(f"Unknown action: {action}")

        # Advance to next player
        self._advance_current()

        return self._check_round_complete()

    def _advance_current(self) -> None:
        """Move current_player_index to next eligible player."""
        players = self.state.players
        n = len(players)
        idx = self.state.current_player_index
        for _ in range(n):
            idx = (idx + 1) % n
            p = players[idx]
            if not p.is_folded and not p.is_all_in and not p.is_sitting_out:
                self.state.current_player_index = idx
                return
        # No more players to act
        self.state.current_player_index = -1

    def _check_round_complete(self) -> BettingResult:
        """Check if the betting round is over."""
        active = [p for p in self.state.players
                  if not p.is_folded and not p.is_sitting_out]

        # All folded except one
        if len(active) <= 1:
            return BettingResult.ALL_FOLDED

        # All remaining are all-in
        can_act = [p for p in active if not p.is_all_in]
        if len(can_act) == 0:
            return BettingResult.ROUND_COMPLETE

        # Round complete if everyone who can act has acted AND bets are equal
        for p in can_act:
            if p.player_id not in self._players_acted:
                return BettingResult.CONTINUE
            if p.bet < self._current_bet:
                return BettingResult.CONTINUE

        return BettingResult.ROUND_COMPLETE

    def current_bet(self) -> int:
        return self._current_bet

    def next_to_act(self) -> Optional[str]:
        """Return player_id of next player to act, or None if round complete."""
        idx = self.state.current_player_index
        if idx == -1:
            return None
        players = self.state.players
        p = players[idx]
        if p.is_folded or p.is_all_in or p.is_sitting_out:
            return None
        return p.player_id
