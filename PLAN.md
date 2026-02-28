# Texas Hold'em Poker Game — Implementation Plan

## Context

Full Texas Hold'em poker game built from scratch. Web-based interface (FastAPI + Vanilla JS), supports both human and AI bot players, and both No-Limit and Fixed-Limit Hold'em variants.

---

## Tech Stack

- **Backend:** FastAPI + uvicorn (WebSockets for real-time game state)
- **Frontend:** Vanilla HTML/CSS/JavaScript (served via Jinja2 templates)
- **Communication:** WebSocket for game events, REST for lobby/setup
- **No external game dependencies** — hand evaluator, AI, and pot logic are pure Python

---

## File Structure

```
poker-game/
├── requirements.txt
├── run.py                          # uvicorn entry point
├── PLAN.md                         # This file
├── app/
│   ├── main.py                     # FastAPI app factory
│   ├── api/
│   │   ├── routes.py               # REST: POST/GET /games
│   │   └── websocket.py            # WS /ws/{game_id}/{player_id} endpoint
│   ├── core/
│   │   ├── card.py                 # Card, Rank, Suit, Deck  ✅
│   │   ├── hand_evaluator.py       # Cactus Kev 7-card evaluator  ✅
│   │   └── pot.py                  # Pot + SidePot management  ✅
│   ├── game/
│   │   ├── game.py                 # PokerGame orchestrator (state machine)  ✅
│   │   ├── game_state.py           # GameState dataclass, GamePhase/GameVariant enums  ✅
│   │   ├── betting.py              # BettingRound (NLHE vs FLHE rules)  ✅
│   │   ├── player.py               # Player dataclass (human + AI)  ✅
│   │   └── rules.py                # Blind posting, dealer rotation  ✅
│   ├── ai/
│   │   ├── bot.py                  # BotPlayer entry point  ✅
│   │   ├── hand_strength.py        # Monte Carlo equity estimator  ✅
│   │   └── strategy.py             # Easy/Medium/Hard decision logic  ✅
│   ├── managers/
│   │   ├── connection_manager.py   # WebSocket registry (game_id -> player_id -> WS)  ✅
│   │   └── game_manager.py         # In-memory PokerGame store  ✅
│   └── models/
│       ├── requests.py             # Pydantic request models  ✅
│       └── events.py               # Pydantic WebSocket event models  ✅
├── static/
│   ├── css/
│   │   ├── table.css               # Felt table, card positions  ✅
│   │   ├── cards.css               # CSS card rendering (Unicode suits)  ✅
│   │   └── controls.css            # Buttons, bet slider  ✅
│   └── js/
│       ├── websocket.js            # WS lifecycle, message dispatch  ✅
│       ├── state.js                # Client-side state store (plain object)  ✅
│       ├── renderer.js             # Idempotent DOM updater  ✅
│       ├── controls.js             # Button/slider event handlers  ✅
│       └── lobby.js                # Lobby page logic  ✅
└── templates/
    ├── base.html                   ✅
    ├── lobby.html                  # Create/join game  ✅
    └── game.html                   # Main table view  ✅
```

---

## Implementation Status

### Phase 1 — Core Engine ✅ COMPLETE
- [x] `card.py` — Card, Rank, Suit, Deck
- [x] `hand_evaluator.py` — Cactus Kev with full lookup tables (scores 1–7462)
- [x] `pot.py` — PotManager + side pot calculation
- [x] Unit tests: 30/30 passing

### Phase 2 — Game State Machine ✅ COMPLETE
- [x] `player.py`, `game_state.py`, `rules.py`
- [x] `betting.py` — NLHE and FLHE rules
- [x] `game.py` — PokerGame async orchestrator

### Phase 3 — AI Bots ✅ COMPLETE
- [x] `hand_strength.py` — Monte Carlo estimator + Chen formula
- [x] `strategy.py` — Easy/Medium/Hard logic
- [x] `bot.py` — wiring

### Phase 4 — FastAPI Backend ✅ COMPLETE
- [x] `connection_manager.py`, `game_manager.py`
- [x] `models/requests.py`, `models/events.py`
- [x] `api/routes.py`, `api/websocket.py`
- [x] `main.py`, `run.py`, `requirements.txt`

### Phase 5 — Frontend ✅ COMPLETE
- [x] `templates/`: base, lobby, game
- [x] `static/css/`: table, cards, controls
- [x] `static/js/`: websocket, state, renderer, controls, lobby

### Phase 6 — Integration & Polish ⏳ TODO
- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Full integration test: `python run.py` → open http://localhost:8000
- [ ] Create game with 2 bots, play 5 hands, verify correct winner
- [ ] Open two browser tabs, verify real-time sync
- [ ] FLHE raise cap enforcement testing
- [ ] Disconnect handling (sit-out, bot takeover)
- [ ] CSS card animations, chip transitions

---

## How to Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start server
python run.py

# 3. Open browser
open http://localhost:8000
```

---

## Key Design Decisions

### Hand Evaluator (Cactus Kev)
- Each card = 32-bit int: rank-bit (one-hot) | suit-bit | rank-nibble | prime
- Flush: check suit bits, look up XOR of rank bits in flush_table
- Non-flush: multiply 5 primes → unique product → look up in unique5 or pairs table
- Scores: 1 (Royal Flush) to 7462 (7-high). **Lower = better**

### WebSocket Security
- `broadcast_personalized()` gives each player their own payload
- Opponent hole cards sent as `["??", "??"]` until showdown
- Only the owning player sees their own hole cards

### Side Pots
- `PotManager` tracks per-player contributions
- `calculate_side_pots()` uses sorted all-in caps to split pots correctly
- Remainder from splitting goes to first winner

### Bot AI
- Easy: Chen formula, rarely raises
- Medium: pot-odds aware, raises good hands
- Hard: Monte Carlo (1000 sims), position-aware, bluffs 15%

---

## Requirements

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.7.0
python-multipart>=0.0.9
jinja2>=3.1.4
```

No NumPy, no database — pure Python game logic.
