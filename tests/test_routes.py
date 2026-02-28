"""Unit tests for routes.py — REST API endpoints."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


class TestLobbyPage:
    def test_lobby_returns_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestCreateGame:
    def test_create_game_default(self):
        resp = client.post("/api/games", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "game_id" in data
        assert data["variant"] == "no_limit"
        assert data["small_blind"] == 10
        assert data["big_blind"] == 20

    def test_create_game_fixed_limit(self):
        resp = client.post("/api/games", json={"variant": "fixed_limit"})
        assert resp.status_code == 200
        assert resp.json()["variant"] == "fixed_limit"

    def test_create_game_with_bots(self):
        resp = client.post("/api/games", json={
            "num_bots": 3,
            "bot_difficulty": "hard",
            "bot_stack": 2000,
        })
        assert resp.status_code == 200
        assert resp.json()["num_bots"] == 3

    def test_create_game_invalid_blinds(self):
        resp = client.post("/api/games", json={
            "small_blind": 20,
            "big_blind": 10,
        })
        assert resp.status_code == 400


class TestJoinGame:
    def _create_game(self) -> str:
        resp = client.post("/api/games", json={"max_players": 4})
        return resp.json()["game_id"]

    def test_join_game(self):
        game_id = self._create_game()
        resp = client.post(f"/api/games/{game_id}/join", json={
            "player_name": "Alice",
            "buy_in": 1000,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Alice"
        assert data["chips"] == 1000
        assert "player_id" in data

    def test_join_game_not_found(self):
        resp = client.post("/api/games/nonexistent/join", json={
            "player_name": "Alice",
            "buy_in": 1000,
        })
        assert resp.status_code == 404

    def test_join_game_buy_in_too_low(self):
        game_id = self._create_game()
        resp = client.post(f"/api/games/{game_id}/join", json={
            "player_name": "Alice",
            "buy_in": 1,  # below min_buy_in (20*20=400)
        })
        assert resp.status_code == 400

    def test_join_game_buy_in_too_high(self):
        game_id = self._create_game()
        resp = client.post(f"/api/games/{game_id}/join", json={
            "player_name": "Alice",
            "buy_in": 999999,  # above max_buy_in (20*200=4000)
        })
        assert resp.status_code == 400


class TestListGames:
    def test_list_games(self):
        resp = client.get("/api/games")
        assert resp.status_code == 200
        assert "games" in resp.json()


class TestGetGameState:
    def test_get_state(self):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        resp = client.get(f"/api/games/{game_id}/state?player_id=test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_id"] == game_id
        assert "phase" in data

    def test_get_state_not_found(self):
        resp = client.get("/api/games/nonexistent/state")
        assert resp.status_code == 404


class TestGamePage:
    def test_game_page(self):
        game_id = client.post("/api/games", json={}).json()["game_id"]
        resp = client.get(f"/game/{game_id}")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_game_page_not_found(self):
        resp = client.get("/game/nonexistent")
        assert resp.status_code == 404


class TestJoinGameFull:
    def test_join_full_game(self):
        # Create a game with max 2 players and 2 bots → already full
        resp = client.post("/api/games", json={
            "max_players": 2,
            "num_bots": 2,
            "bot_stack": 1000,
        })
        game_id = resp.json()["game_id"]
        resp = client.post(f"/api/games/{game_id}/join", json={
            "player_name": "Alice",
            "buy_in": 1000,
        })
        assert resp.status_code == 400
        assert "full" in resp.json()["detail"].lower()
