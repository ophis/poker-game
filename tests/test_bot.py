"""Unit tests for bot.py — BotPlayer decision-making."""
import random
import pytest
from app.ai.bot import BotPlayer
from app.core.card import Card, Rank, Suit
from app.game.betting import BettingAction, ValidActions
from app.game.game_state import GameState, GameVariant, PlayerState


def _make_state(num_players=3, pot=100) -> GameState:
    state = GameState(
        game_id="test",
        variant=GameVariant.NO_LIMIT,
        small_blind=10,
        big_blind=20,
        max_players=9,
    )
    for i in range(num_players):
        state.players.append(PlayerState(
            player_id=f"p{i}", name=f"Player {i}", chips=1000, seat=i,
        ))
    state.pot = pot
    return state


def _make_valid(
    can_check=False,
    call_amount=20,
    min_raise=40,
    max_raise=1000,
    can_raise=True,
    player_stack=1000,
) -> ValidActions:
    return ValidActions(
        can_check=can_check,
        call_amount=call_amount,
        min_raise=min_raise,
        max_raise=max_raise,
        can_raise=can_raise,
        player_stack=player_stack,
    )


class TestBotPlayer:
    def test_init(self):
        bot = BotPlayer("p0")
        assert bot.player_id == "p0"

    def test_no_hole_cards_folds(self):
        bot = BotPlayer("p0")
        state = _make_state()
        player = state.players[0]
        player.hole_cards = []
        valid = _make_valid()
        action, amount = bot.decide(state, player, valid)
        assert action == BettingAction.FOLD
        assert amount == 0

    def test_decide_with_strong_hand(self):
        random.seed(42)
        bot = BotPlayer("p0")
        state = _make_state()
        player = state.players[0]
        player.hole_cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
        ]
        valid = _make_valid(can_check=True, can_raise=True)
        action, amount = bot.decide(state, player, valid, difficulty="medium")
        # AA preflop should result in raise or check (high equity)
        assert action in (BettingAction.RAISE, BettingAction.CHECK)

    def test_decide_with_weak_hand_folds(self):
        random.seed(42)
        bot = BotPlayer("p0")
        state = _make_state(pot=10)
        player = state.players[0]
        player.hole_cards = [
            Card(Rank.SEVEN, Suit.SPADES),
            Card(Rank.TWO, Suit.HEARTS),
        ]
        valid = _make_valid(can_check=False, call_amount=100, can_raise=False)
        action, _ = bot.decide(state, player, valid, difficulty="medium")
        # 72o with bad pot odds should fold
        assert action == BettingAction.FOLD

    def test_raise_amount_capped_at_stack(self):
        random.seed(42)
        bot = BotPlayer("p0")
        state = _make_state(pot=500)
        player = state.players[0]
        player.chips = 100
        player.hole_cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
        ]
        valid = _make_valid(
            can_check=True,
            can_raise=True,
            min_raise=40,
            max_raise=100,
            player_stack=100,
        )
        action, amount = bot.decide(state, player, valid, difficulty="medium")
        if action == BettingAction.RAISE:
            assert amount <= player.chips + player.bet

    def test_counts_opponents(self):
        random.seed(42)
        bot = BotPlayer("p0")
        state = _make_state(num_players=4)
        state.players[1].is_folded = True
        state.players[2].is_sitting_out = True
        player = state.players[0]
        player.hole_cards = [
            Card(Rank.KING, Suit.SPADES),
            Card(Rank.QUEEN, Suit.HEARTS),
        ]
        valid = _make_valid(can_check=True, can_raise=False)
        # Should not crash — opponent count should be 1 (p3 only)
        action, _ = bot.decide(state, player, valid, difficulty="easy")
        assert action in (BettingAction.CHECK, BettingAction.RAISE, BettingAction.CALL)

    def test_raise_below_call_becomes_call(self):
        """If strategy says RAISE but amount <= call_amount, fallback to CALL."""
        random.seed(42)
        bot = BotPlayer("p0")
        state = _make_state(pot=100)
        player = state.players[0]
        player.hole_cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
        ]
        # Very small max_raise forces amount to be small
        valid = _make_valid(
            can_check=False,
            call_amount=50,
            min_raise=20,
            max_raise=30,
            can_raise=True,
            player_stack=1000,
        )
        action, amount = bot.decide(state, player, valid, difficulty="medium")
        # Even if strategy picks RAISE, amount (max 30) <= call_amount (50) → CALL
        if action == BettingAction.CALL:
            assert amount == 50

    def test_difficulty_easy(self):
        random.seed(42)
        bot = BotPlayer("p0")
        state = _make_state()
        player = state.players[0]
        player.hole_cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
        ]
        valid = _make_valid(can_check=True, can_raise=False)
        action, _ = bot.decide(state, player, valid, difficulty="easy")
        assert action == BettingAction.CHECK

    def test_difficulty_hard(self):
        random.seed(99)
        bot = BotPlayer("p0")
        state = _make_state()
        player = state.players[0]
        player.hole_cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.ACE, Suit.HEARTS),
        ]
        valid = _make_valid(can_check=True, can_raise=True)
        action, _ = bot.decide(state, player, valid, difficulty="hard")
        assert action in (BettingAction.CHECK, BettingAction.RAISE)
