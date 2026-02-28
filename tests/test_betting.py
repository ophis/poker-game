"""Unit tests for betting.py — BettingRound logic."""
import pytest
from app.game.betting import BettingAction, BettingResult, BettingRound, ValidActions
from app.game.game_state import GamePhase, GameState, GameVariant, PlayerState


def _make_state(
    num_players=3,
    chips=1000,
    variant=GameVariant.NO_LIMIT,
    big_blind=20,
    small_blind=10,
) -> GameState:
    state = GameState(
        game_id="test",
        variant=variant,
        small_blind=small_blind,
        big_blind=big_blind,
        max_players=9,
    )
    for i in range(num_players):
        state.players.append(PlayerState(
            player_id=f"p{i}",
            name=f"Player {i}",
            chips=chips,
            seat=i,
        ))
    return state


class TestGetValidActions:
    def test_can_check_when_no_bet(self):
        state = _make_state()
        br = BettingRound(state, 0, GamePhase.FLOP)
        valid = br.get_valid_actions("p0")
        assert valid.can_check is True
        assert valid.call_amount == 0

    def test_must_call_when_bet_exists(self):
        state = _make_state()
        state.players[1].bet = 40
        br = BettingRound(state, 0, GamePhase.FLOP)
        valid = br.get_valid_actions("p0")
        assert valid.can_check is False
        assert valid.call_amount == 40

    def test_call_amount_capped_at_stack(self):
        state = _make_state(chips=30)
        state.players[1].bet = 100
        br = BettingRound(state, 0, GamePhase.FLOP)
        valid = br.get_valid_actions("p0")
        assert valid.call_amount == 30  # capped at stack

    def test_nlhe_min_raise(self):
        state = _make_state()
        br = BettingRound(state, 0, GamePhase.PREFLOP)
        valid = br.get_valid_actions("p0")
        # min raise = current_bet + max(last_raise_size, BB) = 0 + 20 = 20
        assert valid.min_raise == 20
        assert valid.max_raise == 1000  # stack + bet (0)
        assert valid.can_raise is True

    def test_nlhe_min_raise_after_raise(self):
        state = _make_state()
        state.players[0].bet = 60
        br = BettingRound(state, 0, GamePhase.PREFLOP)
        br._current_bet = 60
        br._last_raise_size = 40  # raised by 40 over 20
        valid = br.get_valid_actions("p1")
        # min raise = 60 + max(40, 20) = 100
        assert valid.min_raise == 100

    def test_flhe_fixed_bet_preflop(self):
        state = _make_state(variant=GameVariant.FIXED_LIMIT)
        br = BettingRound(state, 0, GamePhase.PREFLOP)
        valid = br.get_valid_actions("p0")
        assert valid.min_raise == 20  # 0 + 1*BB
        assert valid.max_raise == 20  # fixed

    def test_flhe_fixed_bet_turn(self):
        state = _make_state(variant=GameVariant.FIXED_LIMIT)
        br = BettingRound(state, 0, GamePhase.TURN)
        valid = br.get_valid_actions("p0")
        assert valid.min_raise == 40  # 0 + 2*BB
        assert valid.max_raise == 40

    def test_flhe_raise_cap(self):
        state = _make_state(variant=GameVariant.FIXED_LIMIT)
        br = BettingRound(state, 0, GamePhase.FLOP)
        br._num_raises = 4
        valid = br.get_valid_actions("p0")
        assert valid.can_raise is False

    def test_cannot_raise_when_no_chips_beyond_call(self):
        state = _make_state(chips=50)
        state.players[1].bet = 50
        br = BettingRound(state, 0, GamePhase.FLOP)
        valid = br.get_valid_actions("p0")
        assert valid.can_raise is False

    def test_player_not_found_raises(self):
        state = _make_state()
        br = BettingRound(state, 0, GamePhase.FLOP)
        with pytest.raises(ValueError):
            br.get_valid_actions("unknown")


class TestApplyAction:
    def test_fold(self):
        state = _make_state()
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        result = br.apply_action("p0", BettingAction.FOLD)
        assert state.players[0].is_folded is True
        # p1 and p2 still in, so CONTINUE
        assert result == BettingResult.CONTINUE

    def test_fold_leaves_one_player(self):
        state = _make_state(num_players=2)
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        result = br.apply_action("p0", BettingAction.FOLD)
        assert result == BettingResult.ALL_FOLDED

    def test_check(self):
        state = _make_state()
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        result = br.apply_action("p0", BettingAction.CHECK)
        assert result == BettingResult.CONTINUE

    def test_check_invalid_raises(self):
        state = _make_state()
        state.players[1].bet = 40
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        with pytest.raises(ValueError, match="cannot check"):
            br.apply_action("p0", BettingAction.CHECK)

    def test_call(self):
        state = _make_state()
        state.players[1].bet = 40
        state.pot = 40
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        result = br.apply_action("p0", BettingAction.CALL)
        assert state.players[0].chips == 960
        assert state.players[0].bet == 40
        assert state.players[0].total_bet == 40
        assert state.pot == 80

    def test_call_all_in(self):
        state = _make_state(chips=30)
        state.players[1].bet = 100
        state.pot = 100
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        br.apply_action("p0", BettingAction.CALL)
        assert state.players[0].chips == 0
        assert state.players[0].is_all_in is True
        assert state.players[0].bet == 30

    def test_raise_nlhe(self):
        state = _make_state()
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        result = br.apply_action("p0", BettingAction.RAISE, 60)
        assert state.players[0].bet == 60
        assert state.players[0].chips == 940
        assert state.pot == 60
        assert br._current_bet == 60
        assert br._num_raises == 1
        # After a raise, only raiser has acted → CONTINUE
        assert result == BettingResult.CONTINUE

    def test_raise_enforces_minimum(self):
        state = _make_state()
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        # Try raising to 5 (below min_raise of 20)
        br.apply_action("p0", BettingAction.RAISE, 5)
        assert state.players[0].bet >= 20  # enforced minimum

    def test_all_in_action(self):
        state = _make_state(chips=500)
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        br.apply_action("p0", BettingAction.ALL_IN)
        assert state.players[0].chips == 0
        assert state.players[0].bet == 500
        assert state.players[0].is_all_in is True

    def test_player_not_found_raises(self):
        state = _make_state()
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        with pytest.raises(ValueError):
            br.apply_action("unknown", BettingAction.FOLD)


class TestNextToAct:
    def test_returns_player_id(self):
        state = _make_state()
        state.current_player_index = 1
        br = BettingRound(state, 1, GamePhase.FLOP)
        assert br.next_to_act() == "p1"

    def test_returns_none_when_folded(self):
        state = _make_state()
        state.current_player_index = 0
        state.players[0].is_folded = True
        br = BettingRound(state, 0, GamePhase.FLOP)
        assert br.next_to_act() is None

    def test_returns_none_when_all_in(self):
        state = _make_state()
        state.current_player_index = 0
        state.players[0].is_all_in = True
        br = BettingRound(state, 0, GamePhase.FLOP)
        assert br.next_to_act() is None

    def test_returns_none_index_neg1(self):
        state = _make_state()
        state.current_player_index = -1
        br = BettingRound(state, 0, GamePhase.FLOP)
        assert br.next_to_act() is None


class TestCurrentBet:
    def test_initial_zero(self):
        state = _make_state()
        br = BettingRound(state, 0, GamePhase.FLOP)
        assert br.current_bet() == 0

    def test_tracks_after_bet(self):
        state = _make_state()
        state.players[0].bet = 50
        br = BettingRound(state, 0, GamePhase.FLOP)
        assert br.current_bet() == 50


class TestRoundCompletion:
    def test_all_check_completes(self):
        state = _make_state(num_players=2)
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        r1 = br.apply_action("p0", BettingAction.CHECK)
        assert r1 == BettingResult.CONTINUE
        r2 = br.apply_action("p1", BettingAction.CHECK)
        assert r2 == BettingResult.ROUND_COMPLETE

    def test_call_completes_round(self):
        state = _make_state(num_players=2)
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        br.apply_action("p0", BettingAction.RAISE, 40)
        r = br.apply_action("p1", BettingAction.CALL)
        assert r == BettingResult.ROUND_COMPLETE

    def test_all_in_vs_one_completes(self):
        state = _make_state(num_players=2, chips=100)
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        br.apply_action("p0", BettingAction.ALL_IN)
        r = br.apply_action("p1", BettingAction.CALL)
        assert r == BettingResult.ROUND_COMPLETE

    def test_reraise_continues(self):
        state = _make_state(num_players=2)
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        br.apply_action("p0", BettingAction.RAISE, 40)
        r = br.apply_action("p1", BettingAction.RAISE, 80)
        assert r == BettingResult.CONTINUE

    def test_all_folded_except_one(self):
        state = _make_state(num_players=3)
        state.current_player_index = 0
        br = BettingRound(state, 0, GamePhase.FLOP)
        br.apply_action("p0", BettingAction.FOLD)
        r = br.apply_action("p1", BettingAction.FOLD)
        assert r == BettingResult.ALL_FOLDED
