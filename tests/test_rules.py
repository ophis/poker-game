"""Unit tests for rules.py and game_state.py."""
import pytest
from app.game.game_state import GamePhase, GameState, GameVariant, PlayerState
from app.game.rules import (
    advance_dealer,
    first_to_act_postflop,
    first_to_act_preflop,
    get_blind_indices,
    next_active_seat,
    post_blinds,
)


def _make_state(num_players=3, chips=1000, dealer_index=0) -> GameState:
    state = GameState(
        game_id="test",
        variant=GameVariant.NO_LIMIT,
        small_blind=10,
        big_blind=20,
        max_players=9,
    )
    for i in range(num_players):
        state.players.append(PlayerState(
            player_id=f"p{i}", name=f"Player {i}", chips=chips, seat=i,
        ))
    state.dealer_index = dealer_index
    return state


class TestNextActiveSeat:
    def test_wraps_around(self):
        state = _make_state(num_players=3)
        # From index 2, next active should be 0
        assert next_active_seat(state.players, 2) == 0

    def test_skips_sitting_out(self):
        state = _make_state(num_players=3)
        state.players[1].is_sitting_out = True
        # From 0, skip 1 (sitting out), go to 2
        assert next_active_seat(state.players, 0) == 2

    def test_skips_zero_chips(self):
        state = _make_state(num_players=3)
        state.players[1].chips = 0
        assert next_active_seat(state.players, 0) == 2

    def test_returns_neg1_when_no_active(self):
        state = _make_state(num_players=2)
        state.players[0].is_sitting_out = True
        state.players[1].is_sitting_out = True
        assert next_active_seat(state.players, 0) == -1

    def test_single_active_player(self):
        state = _make_state(num_players=3)
        state.players[0].is_sitting_out = True
        state.players[2].is_sitting_out = True
        # From 0, only p1 is active
        assert next_active_seat(state.players, 0) == 1


class TestAdvanceDealer:
    def test_rotates_dealer(self):
        state = _make_state(num_players=3, dealer_index=0)
        new = advance_dealer(state)
        assert new == 1
        assert state.dealer_index == 1

    def test_wraps_around(self):
        state = _make_state(num_players=3, dealer_index=2)
        new = advance_dealer(state)
        assert new == 0

    def test_skips_sitting_out(self):
        state = _make_state(num_players=3, dealer_index=0)
        state.players[1].is_sitting_out = True
        new = advance_dealer(state)
        assert new == 2


class TestGetBlindIndices:
    def test_three_players(self):
        state = _make_state(num_players=3, dealer_index=0)
        sb, bb = get_blind_indices(state)
        # SB = next after dealer = 1, BB = next after SB = 2
        assert sb == 1
        assert bb == 2

    def test_heads_up_dealer_is_sb(self):
        state = _make_state(num_players=2, dealer_index=0)
        sb, bb = get_blind_indices(state)
        # Heads-up: dealer posts SB
        assert sb == 0
        assert bb == 1

    def test_heads_up_other_dealer(self):
        state = _make_state(num_players=2, dealer_index=1)
        sb, bb = get_blind_indices(state)
        assert sb == 1
        assert bb == 0

    def test_skips_sitting_out_players(self):
        state = _make_state(num_players=4, dealer_index=0)
        state.players[1].is_sitting_out = True
        sb, bb = get_blind_indices(state)
        # SB = next active after dealer = 2, BB = next after 2 = 3
        assert sb == 2
        assert bb == 3


class TestPostBlinds:
    def test_deducts_blinds(self):
        state = _make_state(num_players=3, dealer_index=0)
        sb_amt, bb_amt = post_blinds(state)
        assert sb_amt == 10
        assert bb_amt == 20
        # SB is p1, BB is p2
        assert state.players[1].chips == 990
        assert state.players[1].bet == 10
        assert state.players[1].total_bet == 10
        assert state.players[2].chips == 980
        assert state.players[2].bet == 20
        assert state.players[2].total_bet == 20
        assert state.pot == 30

    def test_short_stack_blind(self):
        state = _make_state(num_players=3, dealer_index=0)
        state.players[1].chips = 5  # less than SB
        sb_amt, bb_amt = post_blinds(state)
        assert sb_amt == 5
        assert state.players[1].chips == 0
        assert state.players[1].is_all_in is True

    def test_short_stack_bb(self):
        state = _make_state(num_players=3, dealer_index=0)
        state.players[2].chips = 15  # less than BB
        sb_amt, bb_amt = post_blinds(state)
        assert bb_amt == 15
        assert state.players[2].chips == 0
        assert state.players[2].is_all_in is True


class TestFirstToAct:
    def test_preflop_utg(self):
        state = _make_state(num_players=3, dealer_index=0)
        # BB is p2, UTG = next after BB = p0
        idx = first_to_act_preflop(state)
        assert idx == 0

    def test_postflop_left_of_dealer(self):
        state = _make_state(num_players=3, dealer_index=0)
        idx = first_to_act_postflop(state)
        # First active after dealer(0) = 1
        assert idx == 1

    def test_postflop_skips_sitting_out(self):
        state = _make_state(num_players=3, dealer_index=0)
        state.players[1].is_sitting_out = True
        idx = first_to_act_postflop(state)
        assert idx == 2

    def test_postflop_skips_folded(self):
        # Regression: folded players must be skipped postflop, otherwise
        # _run_betting_round returns ROUND_COMPLETE immediately and the
        # human never gets action buttons.
        state = _make_state(num_players=3, dealer_index=0)
        state.players[1].is_folded = True
        idx = first_to_act_postflop(state)
        assert idx == 2


class TestGameStateProperties:
    def test_active_players(self):
        state = _make_state(num_players=3)
        state.players[1].is_folded = True
        active = state.active_players
        assert len(active) == 2
        assert all(p.player_id != "p1" for p in active)

    def test_active_excludes_sitting_out(self):
        state = _make_state(num_players=3)
        state.players[2].is_sitting_out = True
        active = state.active_players
        assert len(active) == 2

    def test_seated_players(self):
        state = _make_state(num_players=3)
        state.players[0].is_sitting_out = True
        seated = state.seated_players
        assert len(seated) == 2

    def test_current_player(self):
        state = _make_state(num_players=3)
        state.current_player_index = 1
        assert state.current_player.player_id == "p1"

    def test_current_player_out_of_range(self):
        state = _make_state(num_players=3)
        state.current_player_index = -1
        assert state.current_player is None

    def test_get_player_found(self):
        state = _make_state(num_players=3)
        p = state.get_player("p1")
        assert p is not None
        assert p.name == "Player 1"

    def test_get_player_not_found(self):
        state = _make_state(num_players=3)
        assert state.get_player("unknown") is None

    def test_player_index(self):
        state = _make_state(num_players=3)
        assert state.player_index("p2") == 2
        assert state.player_index("unknown") == -1


class TestAdvanceDealerFallback:
    def test_no_active_players_stays(self):
        """When no active seat found, dealer index stays unchanged."""
        state = _make_state(num_players=2, dealer_index=0)
        state.players[0].is_sitting_out = True
        state.players[1].is_sitting_out = True
        new = advance_dealer(state)
        assert new == 0  # fallback


class TestPlayerToDict:
    def test_to_dict(self):
        from app.game.player import Player
        p = Player(
            player_id="p1", name="Alice", chips=1000,
            is_bot=True, bot_difficulty="hard", seat=2, is_connected=True,
        )
        d = p.to_dict()
        assert d["player_id"] == "p1"
        assert d["name"] == "Alice"
        assert d["chips"] == 1000
        assert d["is_bot"] is True
        assert d["bot_difficulty"] == "hard"
        assert d["seat"] == 2
        assert d["is_connected"] is True
