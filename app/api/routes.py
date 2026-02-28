"""REST API routes: lobby, game creation/joining."""
from __future__ import annotations
import uuid
from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.game.game_state import GameVariant
from app.game.player import Player
from app.managers.connection_manager import connection_manager
from app.managers.game_manager import game_manager
from app.models.requests import CreateGameRequest, JoinGameRequest

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def lobby_page(request: Request):
    templates = request.app.state.templates
    games = game_manager.list_games()
    return templates.TemplateResponse(request, "lobby.html", {"games": games})


@router.get("/game/{game_id}", response_class=HTMLResponse)
async def game_page(request: Request, game_id: str):
    templates = request.app.state.templates
    game = game_manager.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return templates.TemplateResponse(request, "game.html", {
        "game_id": game_id,
        "variant": game.state.variant.value,
    })


@router.post("/api/games")
async def create_game(req: CreateGameRequest) -> Dict[str, Any]:
    variant = GameVariant.NO_LIMIT if req.variant == "no_limit" else GameVariant.FIXED_LIMIT

    if req.big_blind < req.small_blind * 2:
        raise HTTPException(status_code=400, detail="big_blind must be >= 2 * small_blind")

    game = game_manager.create_game(
        variant=variant,
        small_blind=req.small_blind,
        big_blind=req.big_blind,
        max_players=req.max_players,
        min_buy_in=req.min_buy_in,
        max_buy_in=req.max_buy_in,
    )

    # Add bots
    for i in range(req.num_bots):
        bot = Player(
            player_id=str(uuid.uuid4())[:8],
            name=f"Bot {i + 1}",
            chips=req.bot_stack,
            is_bot=True,
            bot_difficulty=req.bot_difficulty,
            seat=i,
        )
        game.add_player(bot)

    # Wire broadcast through connection manager
    async def broadcast_cb(game_id, event_type, payload_factory):
        await connection_manager.broadcast_personalized(game_id, event_type, payload_factory)

    game.set_broadcast(broadcast_cb)

    import asyncio
    asyncio.create_task(game.start())

    return {
        "game_id": game.state.game_id,
        "variant": game.state.variant.value,
        "small_blind": game.state.small_blind,
        "big_blind": game.state.big_blind,
        "max_players": game.state.max_players,
        "num_bots": req.num_bots,
    }


@router.post("/api/games/{game_id}/join")
async def join_game(game_id: str, req: JoinGameRequest) -> Dict[str, Any]:
    game = game_manager.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    if len(game.state.players) >= game.state.max_players:
        raise HTTPException(status_code=400, detail="Game is full")

    # Validate buy-in
    if req.buy_in < game.state.min_buy_in:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum buy-in is {game.state.min_buy_in}"
        )
    if req.buy_in > game.state.max_buy_in:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum buy-in is {game.state.max_buy_in}"
        )

    player_id = str(uuid.uuid4())[:8]
    player = Player(
        player_id=player_id,
        name=req.player_name,
        chips=req.buy_in,
        is_bot=False,
        seat=len(game.state.players),
    )
    success = game.add_player(player)
    if not success:
        raise HTTPException(status_code=400, detail="Could not join game")

    return {
        "player_id": player_id,
        "game_id": game_id,
        "name": req.player_name,
        "chips": req.buy_in,
    }


@router.get("/api/games")
async def list_games() -> Dict[str, Any]:
    return {"games": game_manager.list_games()}


@router.get("/api/games/{game_id}/state")
async def get_game_state(game_id: str, player_id: str = "") -> Dict[str, Any]:
    game = game_manager.get_game(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return game.get_state_for_player(player_id)
