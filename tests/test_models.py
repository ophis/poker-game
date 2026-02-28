"""Unit tests for models — Pydantic request/event models."""
import pytest
from pydantic import ValidationError
from app.models.requests import CreateGameRequest, JoinGameRequest
from app.models.events import ClientAction, ActionPayload, ChatPayload, ServerEvent


class TestCreateGameRequest:
    def test_defaults(self):
        req = CreateGameRequest()
        assert req.variant == "no_limit"
        assert req.small_blind == 10
        assert req.big_blind == 20
        assert req.max_players == 6
        assert req.num_bots == 0
        assert req.bot_difficulty == "medium"
        assert req.bot_stack == 1000

    def test_custom_values(self):
        req = CreateGameRequest(
            variant="fixed_limit",
            small_blind=5,
            big_blind=10,
            max_players=4,
            num_bots=3,
            bot_difficulty="hard",
            bot_stack=2000,
            min_buy_in=100,
            max_buy_in=5000,
        )
        assert req.variant == "fixed_limit"
        assert req.num_bots == 3

    def test_invalid_variant(self):
        with pytest.raises(ValidationError):
            CreateGameRequest(variant="pot_limit")

    def test_invalid_bot_difficulty(self):
        with pytest.raises(ValidationError):
            CreateGameRequest(bot_difficulty="impossible")

    def test_max_players_range(self):
        with pytest.raises(ValidationError):
            CreateGameRequest(max_players=1)  # min 2
        with pytest.raises(ValidationError):
            CreateGameRequest(max_players=10)  # max 9


class TestJoinGameRequest:
    def test_valid(self):
        req = JoinGameRequest(player_name="Alice", buy_in=1000)
        assert req.player_name == "Alice"
        assert req.buy_in == 1000

    def test_empty_name(self):
        with pytest.raises(ValidationError):
            JoinGameRequest(player_name="", buy_in=1000)

    def test_zero_buy_in(self):
        with pytest.raises(ValidationError):
            JoinGameRequest(player_name="Alice", buy_in=0)


class TestEventModels:
    def test_client_action(self):
        ca = ClientAction(type="action", payload={"action": "fold"})
        assert ca.type == "action"
        assert ca.payload["action"] == "fold"

    def test_action_payload(self):
        ap = ActionPayload(action="raise", amount=100)
        assert ap.action == "raise"
        assert ap.amount == 100

    def test_action_payload_default_amount(self):
        ap = ActionPayload(action="fold")
        assert ap.amount == 0

    def test_chat_payload(self):
        cp = ChatPayload(message="hello")
        assert cp.message == "hello"

    def test_server_event(self):
        se = ServerEvent(type="game_state", payload={"pot": 100})
        assert se.type == "game_state"
