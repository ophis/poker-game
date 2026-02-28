"""Unit tests for game_manager.py — GameManager CRUD."""
from app.game.game_state import GameVariant
from app.managers.game_manager import GameManager


class TestGameManager:
    def test_create_game(self):
        gm = GameManager()
        game = gm.create_game(
            variant=GameVariant.NO_LIMIT,
            small_blind=10,
            big_blind=20,
        )
        assert game.state.variant == GameVariant.NO_LIMIT
        assert game.state.small_blind == 10
        assert game.state.big_blind == 20
        assert game.state.max_players == 9

    def test_create_game_custom_params(self):
        gm = GameManager()
        game = gm.create_game(
            variant=GameVariant.FIXED_LIMIT,
            small_blind=5,
            big_blind=10,
            max_players=4,
            min_buy_in=100,
            max_buy_in=500,
        )
        assert game.state.variant == GameVariant.FIXED_LIMIT
        assert game.state.max_players == 4
        assert game.state.min_buy_in == 100
        assert game.state.max_buy_in == 500

    def test_get_game(self):
        gm = GameManager()
        game = gm.create_game(GameVariant.NO_LIMIT, 10, 20)
        game_id = game.state.game_id
        retrieved = gm.get_game(game_id)
        assert retrieved is game

    def test_get_game_not_found(self):
        gm = GameManager()
        assert gm.get_game("nonexistent") is None

    def test_list_games_empty(self):
        gm = GameManager()
        assert gm.list_games() == []

    def test_list_games(self):
        gm = GameManager()
        g1 = gm.create_game(GameVariant.NO_LIMIT, 10, 20)
        g2 = gm.create_game(GameVariant.FIXED_LIMIT, 5, 10)
        games = gm.list_games()
        assert len(games) == 2
        game_ids = {g["game_id"] for g in games}
        assert g1.state.game_id in game_ids
        assert g2.state.game_id in game_ids
        # Check fields
        for g in games:
            assert "variant" in g
            assert "phase" in g
            assert "players" in g
            assert "small_blind" in g
            assert "big_blind" in g
            assert "hand_number" in g

    def test_delete_game(self):
        gm = GameManager()
        game = gm.create_game(GameVariant.NO_LIMIT, 10, 20)
        game_id = game.state.game_id
        assert gm.delete_game(game_id) is True
        assert gm.get_game(game_id) is None

    def test_delete_game_not_found(self):
        gm = GameManager()
        assert gm.delete_game("nonexistent") is False
