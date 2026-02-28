"""Unit tests for game.py — PokerGame orchestrator."""
import asyncio
import pytest

from app.core.card import Card, Rank, Suit
from app.game.betting import BettingAction
from app.game.game import PokerGame
from app.game.game_state import GamePhase, GameVariant, PlayerState
from app.game.player import Player


def _make_game(num_players=3, chips=1000) -> PokerGame:
    game = PokerGame(
        game_id="test-001",
        variant=GameVariant.NO_LIMIT,
        small_blind=10,
        big_blind=20,
        max_players=6,
    )
    for i in range(num_players):
        p = Player(player_id=f"p{i}", name=f"Player {i}", chips=chips)
        game.add_player(p)
    return game


class TestAddPlayer:
    def test_add_player_success(self):
        game = _make_game(num_players=0)
        p = Player(player_id="p0", name="Alice", chips=1000)
        assert game.add_player(p) is True
        assert len(game.state.players) == 1
        assert game.state.players[0].player_id == "p0"

    def test_add_player_sets_seat(self):
        game = _make_game(num_players=0)
        p1 = Player(player_id="p0", name="Alice", chips=1000)
        p2 = Player(player_id="p1", name="Bob", chips=1000)
        game.add_player(p1)
        game.add_player(p2)
        assert game.state.players[0].seat == 0
        assert game.state.players[1].seat == 1

    def test_reject_duplicate(self):
        game = _make_game(num_players=1)
        dup = Player(player_id="p0", name="Dup", chips=500)
        assert game.add_player(dup) is False
        assert len(game.state.players) == 1

    def test_reject_when_full(self):
        game = PokerGame(
            game_id="test",
            variant=GameVariant.NO_LIMIT,
            small_blind=10,
            big_blind=20,
            max_players=2,
        )
        game.add_player(Player(player_id="p0", name="A", chips=1000))
        game.add_player(Player(player_id="p1", name="B", chips=1000))
        result = game.add_player(Player(player_id="p2", name="C", chips=1000))
        assert result is False
        assert len(game.state.players) == 2


class TestRemovePlayer:
    def test_remove_in_waiting(self):
        game = _make_game(num_players=2)
        game.state.phase = GamePhase.WAITING
        game.remove_player("p0")
        assert len(game.state.players) == 1
        assert game.state.players[0].player_id == "p1"

    def test_remove_mid_hand_marks_sitting_out(self):
        game = _make_game(num_players=2)
        game.state.phase = GamePhase.FLOP  # mid-hand
        game.remove_player("p0")
        ps = game.state.get_player("p0")
        assert ps.is_sitting_out is True
        assert ps.is_folded is True

    def test_remove_unknown_noop(self):
        game = _make_game(num_players=1)
        game.remove_player("unknown")
        assert len(game.state.players) == 1


class TestGetStateForPlayer:
    def test_own_cards_visible(self):
        game = _make_game(num_players=2)
        game.state.phase = GamePhase.PREFLOP
        # Give players hole cards
        c1 = Card(Rank.ACE, Suit.SPADES)
        c2 = Card(Rank.KING, Suit.HEARTS)
        game.state.players[0].hole_cards = [c1, c2]
        game.state.players[1].hole_cards = [
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.THREE, Suit.DIAMONDS),
        ]

        payload = game.get_state_for_player("p0")
        # Own cards revealed
        p0_data = [p for p in payload["players"] if p["player_id"] == "p0"][0]
        assert p0_data["hole_cards"] == ["As", "Kh"]

    def test_opponent_cards_masked(self):
        game = _make_game(num_players=2)
        game.state.phase = GamePhase.PREFLOP
        game.state.players[0].hole_cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
        ]
        game.state.players[1].hole_cards = [
            Card(Rank.TWO, Suit.CLUBS),
            Card(Rank.THREE, Suit.DIAMONDS),
        ]

        payload = game.get_state_for_player("p0")
        p1_data = [p for p in payload["players"] if p["player_id"] == "p1"][0]
        assert p1_data["hole_cards"] == ["??", "??"]

    def test_payload_includes_game_info(self):
        game = _make_game(num_players=2)
        payload = game.get_state_for_player("p0")
        assert payload["game_id"] == "test-001"
        assert payload["variant"] == "no_limit"
        assert payload["small_blind"] == 10
        assert payload["big_blind"] == 20


class TestSubmitAction:
    def test_submit_sets_event(self):
        async def _run():
            game = _make_game(num_players=2)
            await game.submit_action("p0", BettingAction.FOLD)
            assert game._pending_action == ("p0", BettingAction.FOLD, 0)
        asyncio.run(_run())

    def test_submit_with_amount(self):
        async def _run():
            game = _make_game(num_players=2)
            await game.submit_action("p0", BettingAction.RAISE, 100)
            assert game._pending_action == ("p0", BettingAction.RAISE, 100)
        asyncio.run(_run())


class TestAwardToLastRemaining:
    def test_awards_pot_to_sole_survivor(self):
        async def _run():
            game = _make_game(num_players=2)
            game.state.pot = 100
            game.state.players[0].is_folded = True
            broadcast_calls = []

            async def mock_broadcast(game_id, event_type, factory):
                broadcast_calls.append((event_type, factory("p1")))

            game.set_broadcast(mock_broadcast)
            await game._award_to_last_remaining()
            assert game.state.players[1].chips == 1100
            assert game.state.pot == 0
            assert broadcast_calls[0][0] == "winner"
        asyncio.run(_run())


class TestResetStreetBets:
    def test_resets_all_player_bets(self):
        game = _make_game(num_players=3)
        for p in game.state.players:
            p.bet = 50
        game._reset_street_bets()
        for p in game.state.players:
            assert p.bet == 0


class TestStatePayloadFactory:
    def test_no_current_player(self):
        game = _make_game(num_players=2)
        game.state.current_player_index = -1
        payload = game._state_payload_factory("p0")
        # is_active should be False for all when no current player
        for p in payload["players"]:
            assert p["is_active"] is False

    def test_community_cards_serialized(self):
        game = _make_game(num_players=2)
        game.state.community_cards = [
            Card(Rank.ACE, Suit.SPADES),
            Card(Rank.KING, Suit.HEARTS),
        ]
        payload = game._state_payload_factory("p0")
        assert payload["community_cards"] == ["As", "Kh"]

    def test_active_player_marked(self):
        game = _make_game(num_players=2)
        game.state.current_player_index = 0
        payload = game._state_payload_factory("p0")
        p0 = [p for p in payload["players"] if p["player_id"] == "p0"][0]
        p1 = [p for p in payload["players"] if p["player_id"] == "p1"][0]
        assert p0["is_active"] is True
        assert p1["is_active"] is False


class TestShowdown:
    def test_showdown_awards_best_hand(self):
        async def _run():
            game = _make_game(num_players=2)
            game.state.pot = 200
            game.state.community_cards = [
                Card(Rank.TEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.HEARTS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.TWO, Suit.CLUBS),
                Card(Rank.THREE, Suit.DIAMONDS),
            ]
            # p0 gets a pair of aces
            game.state.players[0].hole_cards = [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.CLUBS),
            ]
            # p1 gets a weak hand
            game.state.players[1].hole_cards = [
                Card(Rank.FOUR, Suit.SPADES),
                Card(Rank.FIVE, Suit.CLUBS),
            ]

            broadcast_calls = []

            async def mock_broadcast(game_id, event_type, factory):
                broadcast_calls.append((event_type, factory("p0")))

            game.set_broadcast(mock_broadcast)
            await game._run_showdown()
            # p0 had better hand, should win pot
            assert game.state.pot == 0
            total_chips = game.state.players[0].chips + game.state.players[1].chips
            assert total_chips == 2200  # 2000 starting + 200 pot
        asyncio.run(_run())

    def test_showdown_split_pot_on_tie(self):
        async def _run():
            game = _make_game(num_players=2)
            game.state.pot = 200
            game.state.community_cards = [
                Card(Rank.ACE, Suit.HEARTS),
                Card(Rank.KING, Suit.HEARTS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.HEARTS),
                Card(Rank.TEN, Suit.HEARTS),
            ]
            # Both players have the same hand (community cards dominate)
            game.state.players[0].hole_cards = [
                Card(Rank.TWO, Suit.SPADES),
                Card(Rank.THREE, Suit.CLUBS),
            ]
            game.state.players[1].hole_cards = [
                Card(Rank.FOUR, Suit.SPADES),
                Card(Rank.FIVE, Suit.CLUBS),
            ]

            async def mock_broadcast(game_id, event_type, factory):
                pass

            game.set_broadcast(mock_broadcast)
            await game._run_showdown()
            assert game.state.pot == 0
            # Both should have gotten 100 each (split)
            assert game.state.players[0].chips == 1100
            assert game.state.players[1].chips == 1100
        asyncio.run(_run())

    def test_showdown_winner_info(self):
        async def _run():
            game = _make_game(num_players=2)
            game.state.pot = 200
            game.state.community_cards = [
                Card(Rank.TEN, Suit.HEARTS),
                Card(Rank.JACK, Suit.HEARTS),
                Card(Rank.QUEEN, Suit.HEARTS),
                Card(Rank.TWO, Suit.CLUBS),
                Card(Rank.THREE, Suit.DIAMONDS),
            ]
            game.state.players[0].hole_cards = [
                Card(Rank.ACE, Suit.SPADES),
                Card(Rank.ACE, Suit.CLUBS),
            ]
            game.state.players[1].hole_cards = [
                Card(Rank.FOUR, Suit.SPADES),
                Card(Rank.FIVE, Suit.CLUBS),
            ]

            winner_data = []

            async def mock_broadcast(game_id, event_type, factory):
                if event_type == "winner":
                    winner_data.append(factory("p0"))

            game.set_broadcast(mock_broadcast)
            await game._run_showdown()
            assert len(winner_data) == 1
            payload = winner_data[0]
            assert "winners" in payload
            assert "all_hands" in payload
            assert len(payload["all_hands"]) == 2
        asyncio.run(_run())
