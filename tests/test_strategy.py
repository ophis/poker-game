"""Unit tests for strategy.py — StrategyEngine."""
import random
import pytest
from app.ai.strategy import StrategyEngine
from app.game.betting import BettingAction, ValidActions
from app.game.game_state import GameState, GameVariant, PlayerState


def _make_state(pot=100, num_players=3, dealer_index=0) -> GameState:
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
    state.dealer_index = dealer_index
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


class TestPotOdds:
    def test_basic_pot_odds(self):
        engine = StrategyEngine()
        state = _make_state(pot=100)
        valid = _make_valid(call_amount=50)
        odds = engine._pot_odds(state, valid)
        # 50 / (100 + 50) = 1/3
        assert abs(odds - 1 / 3) < 0.001

    def test_zero_call_returns_zero(self):
        engine = StrategyEngine()
        state = _make_state(pot=100)
        valid = _make_valid(call_amount=0)
        assert engine._pot_odds(state, valid) == 0.0

    def test_large_call_high_odds(self):
        engine = StrategyEngine()
        state = _make_state(pot=10)
        valid = _make_valid(call_amount=100)
        odds = engine._pot_odds(state, valid)
        # 100 / (10 + 100) ≈ 0.909
        assert odds > 0.9


class TestPotSizeBet:
    def test_half_pot(self):
        engine = StrategyEngine()
        state = _make_state(pot=100)
        valid = _make_valid(call_amount=0, min_raise=20, max_raise=1000)
        result = engine._pot_size_bet(state, 0.5, valid)
        # target = 0 + 100*0.5 = 50, clamped to [20, 1000]
        assert result == 50

    def test_respects_min_raise(self):
        engine = StrategyEngine()
        state = _make_state(pot=10)
        valid = _make_valid(call_amount=0, min_raise=40, max_raise=1000)
        result = engine._pot_size_bet(state, 0.1, valid)
        # target = 0 + 10*0.1 = 1, clamped to min_raise 40
        assert result == 40

    def test_respects_max_raise(self):
        engine = StrategyEngine()
        state = _make_state(pot=10000)
        valid = _make_valid(call_amount=0, min_raise=20, max_raise=500)
        result = engine._pot_size_bet(state, 1.0, valid)
        assert result == 500


class TestIsInPosition:
    def test_dealer_not_in_position_with_3_players(self):
        engine = StrategyEngine()
        state = _make_state(num_players=3, dealer_index=0)
        player = state.players[0]
        # relative = (0 - 0) % 3 = 0, n//2 = 1 → 0 >= 1 is False
        assert engine._is_in_position(state, player) is False

    def test_last_seat_in_position(self):
        engine = StrategyEngine()
        state = _make_state(num_players=3, dealer_index=0)
        player = state.players[2]
        # relative = (2 - 0) % 3 = 2, n//2 = 1 → 2 >= 1 is True
        assert engine._is_in_position(state, player) is True

    def test_middle_seat_in_position(self):
        engine = StrategyEngine()
        state = _make_state(num_players=4, dealer_index=0)
        player = state.players[2]
        # relative = (2 - 0) % 4 = 2, n//2 = 2 → 2 >= 2 is True
        assert engine._is_in_position(state, player) is True


class TestEasyStrategy:
    def test_checks_with_weak_hand(self):
        engine = StrategyEngine()
        state = _make_state()
        valid = _make_valid(can_check=True, can_raise=False)
        action, amount = engine._easy(state, state.players[0], valid, equity=0.3)
        assert action == BettingAction.CHECK
        assert amount == 0

    def test_raises_with_high_equity_can_check(self):
        """Easy bot: equity > 0.7, can_check, can_raise, random < 0.3 → RAISE."""
        engine = StrategyEngine()
        state = _make_state(pot=200)
        valid = _make_valid(can_check=True, can_raise=True)
        found_raise = False
        for seed in range(100):
            random.seed(seed)
            action, amount = engine._easy(state, state.players[0], valid, equity=0.8)
            if action == BettingAction.RAISE:
                found_raise = True
                assert amount >= valid.min_raise
                break
        assert found_raise

    def test_folds_weak_hand_when_must_call(self):
        engine = StrategyEngine()
        state = _make_state()
        valid = _make_valid(can_check=False, call_amount=20)
        random.seed(42)
        action, _ = engine._easy(state, state.players[0], valid, equity=0.2)
        assert action == BettingAction.FOLD

    def test_calls_decent_hand(self):
        engine = StrategyEngine()
        state = _make_state(pot=100)
        valid = _make_valid(can_check=False, call_amount=20, can_raise=False)
        action, _ = engine._easy(state, state.players[0], valid, equity=0.6)
        assert action == BettingAction.CALL

    def test_raises_high_equity_facing_bet(self):
        """Easy bot: equity > 0.7, can_raise, facing bet, random < 0.2 → RAISE."""
        engine = StrategyEngine()
        state = _make_state(pot=200)
        valid = _make_valid(can_check=False, call_amount=20, can_raise=True)
        found_raise = False
        for seed in range(200):
            random.seed(seed)
            action, amount = engine._easy(state, state.players[0], valid, equity=0.8)
            if action == BettingAction.RAISE:
                found_raise = True
                break
        assert found_raise


class TestMediumStrategy:
    def test_raises_strong_hand_can_check(self):
        engine = StrategyEngine()
        state = _make_state()
        valid = _make_valid(can_check=True, can_raise=True)
        action, amount = engine._medium(state, state.players[0], valid, equity=0.8)
        assert action == BettingAction.RAISE
        assert amount > 0

    def test_raises_medium_equity_can_check(self):
        """Medium bot: 0.5 < equity < 0.65, can_check, can_raise, random < 0.3 → RAISE."""
        engine = StrategyEngine()
        state = _make_state(pot=200)
        valid = _make_valid(can_check=True, can_raise=True)
        found_raise = False
        for seed in range(200):
            random.seed(seed)
            action, amount = engine._medium(state, state.players[0], valid, equity=0.55)
            if action == BettingAction.RAISE:
                found_raise = True
                break
        assert found_raise

    def test_folds_below_pot_odds(self):
        engine = StrategyEngine()
        state = _make_state(pot=10)
        valid = _make_valid(can_check=False, call_amount=100, can_raise=False)
        # pot_odds = 100 / (10 + 100) ≈ 0.909, equity 0.5 < 0.909
        action, _ = engine._medium(state, state.players[0], valid, equity=0.5)
        assert action == BettingAction.FOLD

    def test_raises_strong_facing_bet(self):
        """Medium bot: equity > 0.7, can_raise, facing bet → RAISE."""
        engine = StrategyEngine()
        state = _make_state(pot=200)
        valid = _make_valid(can_check=False, call_amount=20, can_raise=True)
        action, amount = engine._medium(state, state.players[0], valid, equity=0.75)
        assert action == BettingAction.RAISE

    def test_raises_medium_facing_bet(self):
        """Medium bot: 0.55 < equity < 0.7, can_raise, random < 0.4 → RAISE."""
        engine = StrategyEngine()
        state = _make_state(pot=200)
        valid = _make_valid(can_check=False, call_amount=20, can_raise=True)
        found_raise = False
        for seed in range(200):
            random.seed(seed)
            action, _ = engine._medium(state, state.players[0], valid, equity=0.6)
            if action == BettingAction.RAISE:
                found_raise = True
                break
        assert found_raise

    def test_calls_above_pot_odds(self):
        engine = StrategyEngine()
        state = _make_state(pot=100)
        valid = _make_valid(can_check=False, call_amount=10, can_raise=False)
        # pot_odds = 10/(100+10) ≈ 0.09, equity 0.5 > 0.09
        action, _ = engine._medium(state, state.players[0], valid, equity=0.5)
        assert action == BettingAction.CALL


class TestHardStrategy:
    def test_raises_strong_hand(self):
        engine = StrategyEngine()
        state = _make_state()
        valid = _make_valid(can_check=True, can_raise=True)
        random.seed(99)  # avoid bluff trigger
        action, _ = engine._hard(state, state.players[0], valid, equity=0.8)
        assert action == BettingAction.RAISE

    def test_bluff_raises_can_check(self):
        """Hard bot: in position, random < 0.15, can_check, can_raise → bluff RAISE."""
        engine = StrategyEngine()
        state = _make_state(num_players=3, dealer_index=0)
        player = state.players[2]  # in position
        valid = _make_valid(can_check=True, can_raise=True)
        found_bluff = False
        for seed in range(200):
            random.seed(seed)
            action, _ = engine._hard(state, player, valid, equity=0.3)
            if action == BettingAction.RAISE:
                found_bluff = True
                break
        assert found_bluff

    def test_bluff_raises_facing_bet(self):
        """Hard bot: in position, random < 0.15, facing bet, can_raise → bluff RAISE."""
        engine = StrategyEngine()
        state = _make_state(num_players=3, dealer_index=0)
        player = state.players[2]  # in position
        valid = _make_valid(can_check=False, call_amount=20, can_raise=True)
        found_bluff = False
        for seed in range(200):
            random.seed(seed)
            action, _ = engine._hard(state, player, valid, equity=0.3)
            if action == BettingAction.RAISE:
                found_bluff = True
                break
        assert found_bluff

    def test_folds_weak_hand_no_bluff(self):
        engine = StrategyEngine()
        state = _make_state(pot=10)
        valid = _make_valid(can_check=False, call_amount=100, can_raise=True)
        random.seed(99)  # no bluff (0.15 threshold)
        action, _ = engine._hard(state, state.players[0], valid, equity=0.01)
        assert action == BettingAction.FOLD

    def test_value_raise_facing_bet(self):
        """Hard bot: equity > 0.75, can_raise, facing bet → value RAISE."""
        engine = StrategyEngine()
        state = _make_state(pot=200)
        valid = _make_valid(can_check=False, call_amount=20, can_raise=True)
        random.seed(999)  # avoid bluff
        action, _ = engine._hard(state, state.players[0], valid, equity=0.8)
        assert action == BettingAction.RAISE

    def test_raise_medium_equity_in_position(self):
        """Hard bot: 0.55 < equity, in_position, 50% chance → RAISE."""
        engine = StrategyEngine()
        state = _make_state(num_players=3, dealer_index=0)
        player = state.players[2]  # in position
        valid = _make_valid(can_check=False, call_amount=20, can_raise=True)
        found_raise = False
        for seed in range(200):
            random.seed(seed)
            action, _ = engine._hard(state, player, valid, equity=0.6)
            if action == BettingAction.RAISE:
                found_raise = True
                break
        assert found_raise

    def test_call_fallback(self):
        """Hard bot: decent equity, not strong enough, no bluff, can_raise=False → CALL."""
        random.seed(999)
        engine = StrategyEngine()
        state = _make_state(pot=200)
        valid = _make_valid(can_check=False, call_amount=20, can_raise=False)
        action, amount = engine._hard(state, state.players[0], valid, equity=0.5)
        assert action == BettingAction.CALL
        assert amount == 20

    def test_decide_routes_to_difficulty(self):
        engine = StrategyEngine()
        state = _make_state()
        valid = _make_valid(can_check=True, can_raise=False)
        action, _ = engine.decide(state, state.players[0], valid, 0.3, "easy")
        assert action == BettingAction.CHECK
        action, _ = engine.decide(state, state.players[0], valid, 0.3, "medium")
        assert action == BettingAction.CHECK
        action, _ = engine.decide(state, state.players[0], valid, 0.3, "hard")
        assert action == BettingAction.CHECK
