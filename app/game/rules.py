"""Blind posting, dealer rotation, and hand setup rules."""
from __future__ import annotations
from typing import List, Tuple

from app.game.game_state import GameState, PlayerState


def next_active_seat(players: List[PlayerState], from_index: int) -> int:
    """Return the index of the next player who is not folded/sitting-out/broke."""
    n = len(players)
    for offset in range(1, n + 1):
        idx = (from_index + offset) % n
        p = players[idx]
        if not p.is_sitting_out and p.chips > 0:
            return idx
    return -1


def advance_dealer(state: GameState) -> int:
    """Move the dealer button to the next valid seat. Returns new dealer index."""
    new_dealer = next_active_seat(state.players, state.dealer_index)
    if new_dealer == -1:
        new_dealer = state.dealer_index  # fallback
    state.dealer_index = new_dealer
    return new_dealer


def get_blind_indices(state: GameState) -> Tuple[int, int]:
    """
    Return (small_blind_index, big_blind_index) given the current dealer.
    Heads-up rule: dealer posts SB, other player posts BB.
    """
    players = state.players
    n_active = sum(1 for p in players if not p.is_sitting_out and p.chips > 0)

    if n_active == 2:
        sb_index = state.dealer_index
    else:
        sb_index = next_active_seat(players, state.dealer_index)

    bb_index = next_active_seat(players, sb_index)
    return sb_index, bb_index


def post_blinds(state: GameState) -> Tuple[int, int]:
    """
    Post blinds for the current hand. Modifies player chips and bets.
    Returns (amount_sb_posted, amount_bb_posted).
    """
    sb_idx, bb_idx = get_blind_indices(state)
    sb_player = state.players[sb_idx]
    bb_player = state.players[bb_idx]

    # Small blind
    sb_amount = min(state.small_blind, sb_player.chips)
    sb_player.chips -= sb_amount
    sb_player.bet = sb_amount
    sb_player.total_bet = sb_amount
    if sb_player.chips == 0:
        sb_player.is_all_in = True

    # Big blind
    bb_amount = min(state.big_blind, bb_player.chips)
    bb_player.chips -= bb_amount
    bb_player.bet = bb_amount
    bb_player.total_bet = bb_amount
    if bb_player.chips == 0:
        bb_player.is_all_in = True

    state.pot += sb_amount + bb_amount
    return sb_amount, bb_amount


def first_to_act_preflop(state: GameState) -> int:
    """Index of first player to act preflop (UTG = one after BB)."""
    _, bb_idx = get_blind_indices(state)
    return next_active_seat(state.players, bb_idx)


def first_to_act_postflop(state: GameState) -> int:
    """Index of first player to act postflop (first active player left of dealer)."""
    return next_active_seat(state.players, state.dealer_index)
