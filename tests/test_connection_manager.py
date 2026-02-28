"""Unit tests for connection_manager.py — ConnectionManager."""
import asyncio
from unittest.mock import AsyncMock, MagicMock
from app.managers.connection_manager import ConnectionManager


def _mock_ws():
    """Create a mock WebSocket."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    return ws


class TestConnect:
    def test_connect_and_is_connected(self):
        async def _run():
            cm = ConnectionManager()
            ws = _mock_ws()
            await cm.connect("game1", "p1", ws)
            assert cm.is_connected("game1", "p1") is True
            ws.accept.assert_awaited_once()
        asyncio.run(_run())

    def test_connect_multiple_players(self):
        async def _run():
            cm = ConnectionManager()
            ws1 = _mock_ws()
            ws2 = _mock_ws()
            await cm.connect("game1", "p1", ws1)
            await cm.connect("game1", "p2", ws2)
            assert cm.player_count("game1") == 2
        asyncio.run(_run())

    def test_not_connected(self):
        cm = ConnectionManager()
        assert cm.is_connected("game1", "p1") is False


class TestDisconnect:
    def test_disconnect(self):
        async def _run():
            cm = ConnectionManager()
            ws = _mock_ws()
            await cm.connect("game1", "p1", ws)
            cm.disconnect("game1", "p1")
            assert cm.is_connected("game1", "p1") is False
        asyncio.run(_run())

    def test_disconnect_removes_empty_game(self):
        async def _run():
            cm = ConnectionManager()
            ws = _mock_ws()
            await cm.connect("game1", "p1", ws)
            cm.disconnect("game1", "p1")
            assert cm.player_count("game1") == 0
        asyncio.run(_run())

    def test_disconnect_nonexistent_noop(self):
        cm = ConnectionManager()
        cm.disconnect("game1", "p1")  # should not raise


class TestSendPersonal:
    def test_send_to_connected_player(self):
        async def _run():
            cm = ConnectionManager()
            ws = _mock_ws()
            await cm.connect("game1", "p1", ws)
            await cm.send_personal("game1", "p1", "test_event", {"key": "val"})
            ws.send_json.assert_awaited_with({"type": "test_event", "payload": {"key": "val"}})
        asyncio.run(_run())

    def test_send_to_disconnected_noop(self):
        async def _run():
            cm = ConnectionManager()
            # Should not raise
            await cm.send_personal("game1", "p1", "test", {})
        asyncio.run(_run())

    def test_send_error_disconnects(self):
        async def _run():
            cm = ConnectionManager()
            ws = _mock_ws()
            ws.send_json.side_effect = Exception("connection lost")
            await cm.connect("game1", "p1", ws)
            await cm.send_personal("game1", "p1", "test", {})
            assert cm.is_connected("game1", "p1") is False
        asyncio.run(_run())


class TestBroadcastPersonalized:
    def test_sends_to_all_players(self):
        async def _run():
            cm = ConnectionManager()
            ws1 = _mock_ws()
            ws2 = _mock_ws()
            await cm.connect("game1", "p1", ws1)
            await cm.connect("game1", "p2", ws2)
            await cm.broadcast_personalized(
                "game1",
                "update",
                lambda pid: {"for": pid},
            )
            ws1.send_json.assert_awaited_with({"type": "update", "payload": {"for": "p1"}})
            ws2.send_json.assert_awaited_with({"type": "update", "payload": {"for": "p2"}})
        asyncio.run(_run())

    def test_skips_none_payloads(self):
        async def _run():
            cm = ConnectionManager()
            ws1 = _mock_ws()
            ws2 = _mock_ws()
            await cm.connect("game1", "p1", ws1)
            await cm.connect("game1", "p2", ws2)
            # Only send to p1
            await cm.broadcast_personalized(
                "game1",
                "update",
                lambda pid: {"data": 1} if pid == "p1" else None,
            )
            ws1.send_json.assert_awaited()
            ws2.send_json.assert_not_awaited()
        asyncio.run(_run())

    def test_empty_game_noop(self):
        async def _run():
            cm = ConnectionManager()
            await cm.broadcast_personalized("game1", "test", lambda pid: {"x": 1})
        asyncio.run(_run())

    def test_safe_send_error_disconnects(self):
        async def _run():
            cm = ConnectionManager()
            ws = _mock_ws()
            ws.send_json.side_effect = Exception("broken pipe")
            await cm.connect("game1", "p1", ws)
            await cm.broadcast_personalized("game1", "test", lambda pid: {"x": 1})
            assert cm.is_connected("game1", "p1") is False
        asyncio.run(_run())


class TestPlayerCount:
    def test_empty(self):
        cm = ConnectionManager()
        assert cm.player_count("game1") == 0

    def test_after_connect(self):
        async def _run():
            cm = ConnectionManager()
            ws = _mock_ws()
            await cm.connect("game1", "p1", ws)
            assert cm.player_count("game1") == 1
        asyncio.run(_run())
