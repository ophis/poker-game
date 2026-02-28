"""
WebSocket connection registry.

Maintains a mapping: game_id → player_id → WebSocket.
Provides personalized broadcast (each player sees only their own hole cards).
"""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # game_id → { player_id → WebSocket }
        self._connections: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, game_id: str, player_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if game_id not in self._connections:
            self._connections[game_id] = {}
        self._connections[game_id][player_id] = websocket
        logger.info(f"Connected: {player_id} in game {game_id}")

    def disconnect(self, game_id: str, player_id: str) -> None:
        if game_id in self._connections:
            self._connections[game_id].pop(player_id, None)
            if not self._connections[game_id]:
                del self._connections[game_id]
        logger.info(f"Disconnected: {player_id} from game {game_id}")

    async def send_personal(
        self,
        game_id: str,
        player_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        """Send a message to a specific player."""
        ws = self._connections.get(game_id, {}).get(player_id)
        if ws:
            try:
                await ws.send_json({"type": event_type, "payload": payload})
            except Exception as e:
                logger.warning(f"Failed to send to {player_id}: {e}")
                self.disconnect(game_id, player_id)

    async def broadcast_personalized(
        self,
        game_id: str,
        event_type: str,
        payload_factory: Callable[[str], Optional[dict]],
    ) -> None:
        """
        Broadcast to all connected players in a game, with personalized payloads.

        payload_factory(player_id) → dict | None
        If factory returns None, skip that player.
        """
        connections = self._connections.get(game_id, {})
        tasks = []
        for player_id, ws in list(connections.items()):
            payload = payload_factory(player_id)
            if payload is None:
                continue
            tasks.append(self._safe_send(ws, game_id, player_id, event_type, payload))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_send(
        self,
        ws: WebSocket,
        game_id: str,
        player_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        try:
            await ws.send_json({"type": event_type, "payload": payload})
        except Exception as e:
            logger.warning(f"WS send failed {player_id}: {e}")
            self.disconnect(game_id, player_id)

    def is_connected(self, game_id: str, player_id: str) -> bool:
        return player_id in self._connections.get(game_id, {})

    def player_count(self, game_id: str) -> int:
        return len(self._connections.get(game_id, {}))


# Global singleton
connection_manager = ConnectionManager()
