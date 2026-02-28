# Texas Hold'em Poker

A full-featured Texas Hold'em poker game with a web UI, AI bots, and real-time multiplayer — built entirely in Python with no game-logic dependencies.

Supports both **No-Limit** and **Fixed-Limit** Hold'em. Human players connect via browser; AI bots play automatically at three difficulty levels.

---

## Features

- **No-Limit and Fixed-Limit Hold'em** — full rule enforcement for both variants
- **AI bots** at Easy / Medium / Hard difficulty (configurable per game)
- **Real-time multiplayer** — up to 9 players via WebSocket; multiple human players can join the same table from separate browsers
- **Side pot handling** — correct pot splitting for all-in scenarios with multiple players
- **Pure CSS card rendering** — Unicode suit symbols, no image files required
- **In-browser lobby** — create games, set blinds/buy-ins, add bots, join open games

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + uvicorn |
| Real-time comms | WebSockets (FastAPI native) |
| Templates | Jinja2 |
| Frontend | Vanilla HTML / CSS / JavaScript |
| Hand evaluator | Cactus Kev (pure Python) |
| AI | Monte Carlo equity + Chen formula |
| Data validation | Pydantic v2 |
| Storage | In-memory (no database) |

---

## Quick Start

**Requirements:** Python 3.9+

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
python3 run.py

# 3. Open the lobby
open http://localhost:8000
```

From the lobby, create a game (choose variant, blinds, number of bots) and you'll be taken directly to the table.

To play with a second human player, open `http://localhost:8000` in another browser tab or on another device on the same network, and join the game from the lobby.

---

## Running Tests

```bash
python3 -m pytest tests/ -v
```

The test suite covers the hand evaluator and pot manager — the two most critical correctness requirements:

```
tests/test_hand_evaluator.py   21 tests  (eval_5, eval_7, card encoding, rank strings)
tests/test_pot.py               9 tests  (basic pot, side pots, folded player eligibility)
```

---

## Project Structure

```
poker-game/
├── run.py                          # Entry point — starts uvicorn on port 8000
├── requirements.txt
├── app/
│   ├── main.py                     # FastAPI app factory, mounts static/templates
│   ├── core/
│   │   ├── card.py                 # Card, Rank, Suit enums, Deck
│   │   ├── hand_evaluator.py       # Cactus Kev 7-card evaluator
│   │   └── pot.py                  # PotManager + side pot calculation
│   ├── game/
│   │   ├── game.py                 # PokerGame async orchestrator
│   │   ├── game_state.py           # GameState dataclass, GamePhase/GameVariant enums
│   │   ├── betting.py              # BettingRound — NLHE and FLHE rule enforcement
│   │   ├── player.py               # Player dataclass
│   │   └── rules.py                # Blind posting, dealer rotation
│   ├── ai/
│   │   ├── bot.py                  # BotPlayer — wires estimator + strategy
│   │   ├── hand_strength.py        # Monte Carlo equity estimator, Chen formula
│   │   └── strategy.py             # Easy / Medium / Hard decision logic
│   ├── managers/
│   │   ├── connection_manager.py   # WebSocket registry, personalized broadcast
│   │   └── game_manager.py         # In-memory game store
│   ├── models/
│   │   ├── requests.py             # Pydantic models for REST endpoints
│   │   └── events.py               # Pydantic models for WebSocket events
│   └── api/
│       ├── routes.py               # REST: lobby, create/join game, game state
│       └── websocket.py            # WS: /ws/{game_id}/{player_id}
├── static/
│   ├── css/
│   │   ├── table.css               # Felt table, seat positions, overlays
│   │   ├── cards.css               # CSS card rendering (Unicode suits)
│   │   └── controls.css            # Action buttons, raise slider, forms
│   └── js/
│       ├── state.js                # Client state store — never touches DOM
│       ├── renderer.js             # Idempotent DOM updater — reads state only
│       ├── controls.js             # Button/slider event handlers
│       ├── websocket.js            # WS lifecycle, event dispatch
│       └── lobby.js                # Lobby create/join logic
└── templates/
    ├── base.html
    ├── lobby.html                  # Game creation and open-game list
    └── game.html                   # Main poker table
```

---

## Architecture

### Game State Machine

Each hand follows a strict phase sequence:

```
WAITING → STARTING → PREFLOP → FLOP → TURN → RIVER → SHOWDOWN → HAND_OVER → (loop)
                                                    ↑
                                          ALL_FOLDED shortcut (any street)
```

`PokerGame` is an async class that drives the state machine. Bot actions are scheduled with `asyncio.create_task` and a random delay (`0.5–2.0 s`) to simulate thinking time. Human actions arrive via WebSocket and are submitted through an `asyncio.Event` queue.

### Hand Evaluator (Cactus Kev)

Each card is encoded as a 32-bit integer:

```
+--------+--------+--------+--------+
|xxxbbbbb|bbbbbbbb|cdhsrrrr|xxpppppp|
+--------+--------+--------+--------+
  b = one-hot rank bit (bit 16 + rank index)
  cdhs = suit flags (bits 12–15)
  rrrr = rank nibble (bits 8–11)
  pppppp = unique prime per rank (bits 0–5)
```

Evaluation works in two paths:
- **Flush:** OR all cards' suit bits → single suit → XOR rank bits → flush lookup table
- **Non-flush:** multiply 5 prime numbers → unique product → unique5 or pairs lookup table

Scores run from **1** (Royal Flush) to **7462** (7-high). Lower is better. All lookup tables are built once at module import from first principles — no external data files.

`eval_7(cards)` tests all 21 five-card combinations (C(7,5)) and returns the best score.

### Pot and Side Pots

`PotManager` tracks each player's total contribution to the pot. When any player goes all-in, `calculate_side_pots()` splits the pot by iterating through sorted all-in cap levels:

- **Pot 1** (up to smallest all-in): all contributing players eligible
- **Pot 2** (next cap): players who matched the second all-in level eligible
- **Main pot**: remaining chips, eligible only to players who matched in full

The total of all side pots always equals the total chips contributed.

### WebSocket Security

All game state broadcasts are **personalized per player** — each connection receives its own copy of the payload. Opponent hole cards are sent as `["??", "??"]` until showdown. Only the owning player ever sees their own hole cards in the payload.

```python
# connection_manager.py
async def broadcast_personalized(game_id, event_type, payload_factory):
    for player_id, ws in connections[game_id].items():
        payload = payload_factory(player_id)   # unique per player
        await ws.send_json({"type": event_type, "payload": payload})
```

### AI Bots

| Difficulty | Preflop equity | Postflop equity | Bluffing |
|---|---|---|---|
| Easy | Chen formula (normalized) | 100 MC sims | No |
| Medium | Chen formula | 300 MC sims | No |
| Hard | 1000 MC sims | 1000 MC sims | Yes (~15% in position) |

The **Chen formula** assigns a score (0–20) to a two-card hand based on rank, suitedness, connectedness, and gaps — fast enough to run synchronously. Monte Carlo simulation randomly deals out the remaining community cards and opponent hands, then measures win rate over many trials.

The **strategy engine** layers on top of equity:
- Computes pot odds (minimum equity needed for a breakeven call)
- Scales raise sizes as fractions of the pot (½ pot, pot, all-in)
- Hard bots add position awareness (acting last = in position = more aggressive)

### Frontend Architecture

The JavaScript is split into three strictly separated layers:

| Module | Responsibility |
|---|---|
| `state.js` | Plain object store — never reads or writes the DOM |
| `renderer.js` | Reads state, writes DOM idempotently — never holds its own state |
| `controls.js` | Event listeners only — reads state, calls `PokerWS.sendAction()` |

`websocket.js` dispatches incoming events to `GameState` then calls `Renderer.render()`. This separation means the DOM is always a pure function of the state object, making it straightforward to reason about what the player sees at any moment.

---

## REST API

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Lobby page (HTML) |
| `GET` | `/game/{game_id}` | Game table page (HTML) |
| `POST` | `/api/games` | Create a new game |
| `POST` | `/api/games/{id}/join` | Join a game as a human player |
| `GET` | `/api/games` | List all active games |
| `GET` | `/api/games/{id}/state` | Get current game state for a player |

### Create Game — `POST /api/games`

```json
{
  "variant": "no_limit",
  "small_blind": 10,
  "big_blind": 20,
  "max_players": 6,
  "num_bots": 2,
  "bot_difficulty": "medium",
  "bot_stack": 1000
}
```

### Join Game — `POST /api/games/{game_id}/join`

```json
{
  "player_name": "Alice",
  "buy_in": 1000
}
```

Returns `player_id` which must be stored client-side (in `sessionStorage`) for WebSocket authentication.

---

## WebSocket Protocol

Connect: `ws://localhost:8000/ws/{game_id}/{player_id}`

### Server → Client events

| Event | When sent | Key fields |
|---|---|---|
| `game_state` | On connect and phase changes | Full state snapshot |
| `hand_starting` | New hand begins | Reset state |
| `community_card` | Flop / turn / river dealt | Updated community cards |
| `your_turn` | It's this player's turn | `valid_actions` with bet limits |
| `action_taken` | Any player acts | `player_id`, `action`, `pot` |
| `winner` | Hand resolved | `winners` array with amounts and hand names |
| `hand_over` | Hand complete | Final state |
| `chat` | Chat message | `player_id`, `message` |

### Client → Server messages

```json
{ "type": "action", "payload": { "action": "raise", "amount": 120 } }
{ "type": "chat",   "payload": { "message": "nice hand" } }
```

Valid actions: `fold`, `check`, `call`, `raise`, `all_in`.

---

## Fixed-Limit Hold'em Rules

When variant is `fixed_limit`:
- **Preflop / Flop:** bet size = 1 big blind
- **Turn / River:** bet size = 2 big blinds
- **Maximum 4 raises per street** (cap), after which only calls and folds are allowed
- All-in is still permitted when a player's stack is smaller than the fixed bet

---

## Limitations / Known Gaps

- **No persistence** — games live in memory only; restarting the server clears everything
- **No authentication** — `player_id` is a short UUID stored in `sessionStorage`; anyone who knows a `player_id` can act as that player
- **Disconnected human players** are marked as sitting-out but are not replaced by bots
- **No ante or straddle** support
- **No tournament mode** — cash game only (rebuy not implemented)
