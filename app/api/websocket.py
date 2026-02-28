"""WebSocket endpoint for real-time game events."""
from __future__ import annotations
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.game.betting import BettingAction
from app.managers.connection_manager import connection_manager
from app.managers.game_manager import game_manager

logger = logging.getLogger(__name__)
ws_router = APIRouter()


@ws_router.websocket("/ws/{game_id}/{player_id}")
async def websocket_endpoint(websocket: WebSocket, game_id: str, player_id: str):
    game = game_manager.get_game(game_id)
    if not game:
        await websocket.close(code=4004, reason="Game not found")
        return

    await connection_manager.connect(game_id, player_id, websocket)

    # Send current game state immediately on connect
    state_payload = game.get_state_for_player(player_id)
    await connection_manager.send_personal(game_id, player_id, "game_state", state_payload)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            payload = data.get("payload", {})

            if msg_type == "action":
                action_str = payload.get("action", "fold")
                amount = int(payload.get("amount", 0))

                action_map = {
                    "fold": BettingAction.FOLD,
                    "check": BettingAction.CHECK,
                    "call": BettingAction.CALL,
                    "raise": BettingAction.RAISE,
                    "all_in": BettingAction.ALL_IN,
                }
                action = action_map.get(action_str, BettingAction.FOLD)
                await game.submit_action(player_id, action, amount)

            elif msg_type == "chat":
                message = str(payload.get("message", ""))[:200]
                # Broadcast chat to all players
                await connection_manager.broadcast_personalized(
                    game_id,
                    "chat",
                    lambda pid, _pid=player_id, _msg=message: {
                        "player_id": _pid,
                        "message": _msg,
                    },
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        connection_manager.disconnect(game_id, player_id)
        game.remove_player(player_id)
        logger.info(f"Player {player_id} disconnected from game {game_id}")
    except Exception as e:
        logger.error(f"WebSocket error for {player_id} in {game_id}: {e}")
        connection_manager.disconnect(game_id, player_id)
