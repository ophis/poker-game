# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server (port 8000, auto-reload)
python run.py

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_hand_evaluator.py -v

# Run a single test case
python -m pytest tests/test_hand_evaluator.py::TestEval5::test_royal_flush_score_1 -v

# Quick import/startup check
python -c "from app.main import app; print(app.title)"
```

## Architecture

This is a Texas Hold'em poker game with a FastAPI backend, WebSocket real-time communication, and vanilla JS frontend. No external game-logic dependencies — hand evaluator, AI, and pot management are pure Python.

### Game State Machine

`PokerGame` (app/game/game.py) is the async orchestrator driving this state machine:

```
WAITING → STARTING → PREFLOP → FLOP → TURN → RIVER → SHOWDOWN → HAND_OVER → (loop)
                                                   ↑
                                        ALL_FOLDED shortcut (any street)
```

Human actions arrive via WebSocket → `submit_action()` → `asyncio.Event`. Bot actions are scheduled via `asyncio.create_task()` with a random 0.5–2s delay.

### Hand Evaluator (Cactus Kev)

Cards are 32-bit integers encoding rank-bit (one-hot), suit flags, rank nibble, and a unique prime per rank. Evaluation:
- **Flush path**: OR suit bits → single suit → XOR rank bits → flush lookup table
- **Non-flush path**: multiply 5 primes → unique product → pairs/unique5 lookup table

Scores: 1 (Royal Flush) to 7462 (7-high). **Lower is always better.** All lookup tables are built at module import.

### WebSocket Security

`connection_manager.broadcast_personalized()` calls a factory function with each connected player's ID, producing a unique payload per recipient. Opponent hole cards are always `["??", "??"]` in game state snapshots. The only place actual opponent cards are revealed is via the `winner` event at showdown — never through `game_state` snapshots (this prevents a race condition where connecting during SHOWDOWN phase would leak cards).

### Betting

`BettingRound` (app/game/betting.py) manages one street. It mutates `GameState` in place and returns `BettingResult` (CONTINUE | ROUND_COMPLETE | ALL_FOLDED). NLHE min-raise = max(last_raise_size, big_blind). FLHE uses fixed bet sizes (1BB preflop/flop, 2BB turn/river) with a 4-raise-per-street cap.

### AI Bots

`BotPlayer` wires `HandStrengthEstimator` (Monte Carlo equity or Chen formula) with `StrategyEngine` (pot-odds → action decision). Hard bots add position awareness and ~15% bluff frequency.

### Frontend

Vanilla JS with strict three-layer separation:
- **state.js**: plain object store, never touches DOM
- **renderer.js**: idempotent DOM updater, reads state only
- **controls.js**: event listeners, calls `PokerWS.sendAction()`

## Python 3.9 Constraint

Multi-value Enums **must** use `__new__` to set `_value_`. Using `__init__` with `self.value = ...` will raise `AttributeError: can't set attribute`:

```python
class Rank(Enum):
    def __new__(cls, rank_value, symbol, prime):
        obj = object.__new__(cls)
        obj._value_ = rank_value  # NOT self.value
        obj.symbol = symbol
        obj.prime = prime
        return obj
    ACE = (14, "A", 41)
```

Access rank integer via `rank._value_`, not `rank.value` (the latter returns the tuple in some contexts).
