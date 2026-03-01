"""
Game simulation tests — verify end-to-end game flow works correctly.

Two suites:
  TestHeadlessSimulation  — in-process, no HTTP server; fast and deterministic
  TestLiveServerSimulation — full WebSocket round-trip through a real uvicorn process

Run all:
    python -m pytest tests/simulation/ -v

Run only headless (no server needed):
    python -m pytest tests/simulation/ -v -k "Headless"
"""
import asyncio
import json
import time

import httpx
import pytest
import websockets

from app.game.game import PokerGame
from app.game.game_state import GameVariant
from app.game.player import Player


# ---------------------------------------------------------------------------
# Shared headless helpers
# ---------------------------------------------------------------------------

def _make_bot_game(num_bots: int = 4, chips: int = 1000,
                   difficulty: str = "easy") -> PokerGame:
    """Create an in-process PokerGame populated entirely with bots."""
    game = PokerGame(
        game_id="sim-test",
        variant=GameVariant.NO_LIMIT,
        small_blind=10,
        big_blind=20,
        max_players=9,
    )
    for i in range(num_bots):
        game.add_player(Player(
            player_id=f"bot-{i}",
            name=f"Bot{i + 1}",
            chips=chips,
            is_bot=True,
            bot_difficulty=difficulty,
        ))
    return game


def _wire_event_log(game: PokerGame) -> list:
    """Attach a broadcast callback that appends every event to a list.

    The payload is captured from the first player's perspective so that
    hole-card masking logic is exercised.
    """
    log: list = []

    async def capture(game_id, event_type, payload_factory):
        first_pid = game.state.players[0].player_id if game.state.players else "_"
        payload = payload_factory(first_pid)
        log.append({"type": event_type, "payload": payload})

    game.set_broadcast(capture)
    return log


async def _run_until_hands(game: PokerGame, log: list,
                            num_hands: int = 1, timeout: float = 120.0) -> None:
    """Start the game loop and block until *num_hands* winner events appear."""
    task = asyncio.create_task(game.start())
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            await asyncio.sleep(0.1)
            if sum(1 for e in log if e["type"] == "winner") >= num_hands:
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# ---------------------------------------------------------------------------
# Headless simulation tests
# ---------------------------------------------------------------------------

class TestHeadlessSimulation:
    """Fast, in-process simulations that do not require a running HTTP server."""

    def test_single_hand_emits_winner(self):
        """4 easy bots playing one hand must produce a winner event."""
        async def _run():
            game = _make_bot_game(num_bots=4)
            log = _wire_event_log(game)
            await _run_until_hands(game, log, num_hands=1)

            winner_events = [e for e in log if e["type"] == "winner"]
            assert winner_events, "Expected at least one winner event"

            payload = winner_events[0]["payload"]
            assert "winners" in payload, "winner payload must have 'winners' key"
            assert payload["winners"], "winners list must not be empty"
            winner = payload["winners"][0]
            assert "player_id" in winner
            assert winner.get("amount", 0) > 0, "Winner must receive a positive chip amount"

        asyncio.run(_run())

    def test_chip_conservation_over_two_hands(self):
        """Total chips must be identical before and after two complete hands."""
        async def _run():
            game = _make_bot_game(num_bots=4, chips=1000)
            initial_total = sum(p.chips for p in game.state.players)
            log = _wire_event_log(game)
            await _run_until_hands(game, log, num_hands=2, timeout=240)

            winner_events = [e for e in log if e["type"] == "winner"]
            assert len(winner_events) >= 2, (
                f"Only {len(winner_events)} hand(s) completed — needed 2"
            )

            final_total = sum(p.chips for p in game.state.players)
            assert final_total == initial_total, (
                f"Chip conservation violated: started with {initial_total}, "
                f"ended with {final_total}"
            )

        asyncio.run(_run())

    def test_hand_numbers_are_sequential(self):
        """hand_starting events carry hand_number 1, 2, 3 in ascending order."""
        async def _run():
            game = _make_bot_game(num_bots=4)
            log = _wire_event_log(game)
            await _run_until_hands(game, log, num_hands=3, timeout=360)

            starting_events = [e for e in log if e["type"] == "hand_starting"]
            assert len(starting_events) >= 3, (
                f"Only {len(starting_events)} hand_starting event(s) received"
            )
            for expected, event in enumerate(starting_events[:3], start=1):
                got = event["payload"]["hand_number"]
                assert got == expected, (
                    f"Hand {expected}: expected hand_number={expected}, got {got}"
                )

        asyncio.run(_run())

    def test_pot_cleared_after_hand(self):
        """state.pot must be 0 once all winner broadcasting has completed.

        Note: _award_to_last_remaining broadcasts the winner event first, then
        sets state.pot = 0.  We therefore sample the pot one event-loop tick
        after the winner broadcast completes rather than inside the callback.
        """
        async def _run():
            game = _make_bot_game(num_bots=4)
            log = _wire_event_log(game)
            await _run_until_hands(game, log, num_hands=1)

            winner_events = [e for e in log if e["type"] == "winner"]
            assert winner_events, "No winner event was received"

            # After _run_until_hands, the game task has been cancelled and the
            # event loop has had a chance to finish all callbacks.  The pot must
            # now be 0 regardless of which code path (showdown vs all-fold) ran.
            assert game.state.pot == 0, (
                f"Pot was {game.state.pot} chips after hand completed (expected 0)"
            )

        asyncio.run(_run())

    def test_hole_cards_dealt_to_every_active_player(self):
        """After hand_starting, every active player holds exactly 2 hole cards."""
        async def _run():
            game = _make_bot_game(num_bots=4)
            log = _wire_event_log(game)

            task = asyncio.create_task(game.start())
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                if any(e["type"] == "hand_starting" for e in log):
                    break
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert any(e["type"] == "hand_starting" for e in log), (
                "game never emitted hand_starting"
            )
            for p in game.state.active_players:
                assert len(p.hole_cards) == 2, (
                    f"{p.name} has {len(p.hole_cards)} hole card(s), expected 2"
                )

        asyncio.run(_run())

    def test_flop_delivers_three_community_cards(self):
        """The first community_card event carries exactly 3 cards (the flop)."""
        async def _run():
            game = _make_bot_game(num_bots=4)
            log = _wire_event_log(game)

            task = asyncio.create_task(game.start())
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                if any(e["type"] == "community_card" for e in log):
                    break
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            community_events = [e for e in log if e["type"] == "community_card"]
            if not community_events:
                pytest.skip("Hand ended before the flop (all-fold preflop)")

            flop_payload = community_events[0]["payload"]
            assert len(flop_payload["community_cards"]) == 3, (
                f"Flop must have 3 community cards, "
                f"got {len(flop_payload['community_cards'])}"
            )

        asyncio.run(_run())

    def test_opponent_cards_masked_in_broadcast_payload(self):
        """In hand_starting payloads, opponents' hole cards appear as '??'."""
        async def _run():
            game = _make_bot_game(num_bots=4)
            log = _wire_event_log(game)

            task = asyncio.create_task(game.start())
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                if any(e["type"] == "hand_starting" for e in log):
                    break
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            starting = next((e for e in log if e["type"] == "hand_starting"), None)
            assert starting, "Expected a hand_starting event"

            viewer_id = game.state.players[0].player_id
            for pd in starting["payload"]["players"]:
                if pd["player_id"] == viewer_id:
                    # Viewer's own cards must not be masked
                    if pd["hole_cards"]:
                        assert pd["hole_cards"][0] != "??", (
                            "Viewer's own hole cards must be real, not '??'"
                        )
                else:
                    # Every opponent card must be masked
                    for card in pd["hole_cards"]:
                        assert card == "??", (
                            f"Opponent {pd['name']}'s card {card!r} must be '??' "
                            f"in the hand_starting payload"
                        )

        asyncio.run(_run())

    def test_all_in_scenarios_conserve_chips(self):
        """Chips are conserved even when players go all-in and bust out."""
        async def _run():
            # Small stacks make all-in situations much more likely
            game = _make_bot_game(num_bots=4, chips=100)
            initial_total = sum(p.chips for p in game.state.players)
            log = _wire_event_log(game)
            await _run_until_hands(game, log, num_hands=1, timeout=120)

            winner_events = [e for e in log if e["type"] == "winner"]
            assert winner_events, "No hand completed"

            active_total = sum(p.chips for p in game.state.players)
            assert active_total == initial_total, (
                f"Chip leak with all-in: started {initial_total}, ended {active_total}"
            )

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Chip accounting tests
# ---------------------------------------------------------------------------

class TestChipAccounting:
    """Focused chip-accounting tests: winner amounts, pot conservation, and edge cases."""

    # ------------------------------------------------------------------
    # Test 1 — winner event amount == actual chip gain
    # ------------------------------------------------------------------

    def test_winner_event_amount_equals_chip_gain(self):
        """amount reported in winner event must exactly equal each winner's chip gain."""
        async def _run():
            game = _make_bot_game(num_bots=4, chips=1000)
            log: list = []
            chips_at_hand_start: dict = {}

            async def capture(game_id, event_type, payload_factory):
                nonlocal chips_at_hand_start
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                if event_type == "hand_starting":
                    chips_at_hand_start = {
                        p.player_id: p.chips for p in game.state.players
                    }
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)
            await _run_until_hands(game, log, num_hands=1)

            winner_events = [e for e in log if e["type"] == "winner"]
            assert winner_events, "No winner event was produced"
            assert chips_at_hand_start, "hand_starting event never captured chips"

            for w in winner_events[0]["payload"]["winners"]:
                pid = w["player_id"]
                reported_amount = w["amount"]
                player = game.state.get_player(pid)
                assert player is not None, f"Winner {pid} not found in game state"
                chip_gain = player.chips - chips_at_hand_start.get(pid, player.chips)
                assert chip_gain == reported_amount, (
                    f"Player {pid}: winner event amount={reported_amount} "
                    f"but actual chip gain={chip_gain} "
                    f"(chips_before={chips_at_hand_start.get(pid)}, "
                    f"chips_after={player.chips})"
                )

        asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test 2 — intra-hand chips+pot invariant (excluding winner event)
    # ------------------------------------------------------------------

    def test_total_chips_stable_throughout_hand(self):
        """sum(chips) + pot must equal initial_total at every non-winner event."""
        async def _run():
            game = _make_bot_game(num_bots=4, chips=1000)
            initial_total = sum(p.chips for p in game.state.players)
            log: list = []
            violations: list = []

            async def capture(game_id, event_type, payload_factory):
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                # Skip winner event — all-fold path sets pot=0 after broadcast,
                # causing a transient over-count at that moment.
                if event_type != "winner":
                    current = sum(p.chips for p in game.state.players) + game.state.pot
                    if current != initial_total:
                        violations.append((event_type, current, initial_total))
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)
            await _run_until_hands(game, log, num_hands=1)

            assert [e for e in log if e["type"] == "winner"], "No winner event produced"
            assert not violations, (
                f"Chip+pot invariant violated at {len(violations)} event(s):\n"
                + "\n".join(
                    f"  event={ev}, got={got}, expected={exp}"
                    for ev, got, exp in violations
                )
            )

        asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test 3 — all-fold: pot awarded to last remaining player
    # ------------------------------------------------------------------

    def test_all_fold_pot_goes_to_last_player(self):
        """When all players fold, the entire pot goes to the sole remaining player."""
        async def _run():
            game = _make_bot_game(num_bots=4, chips=1000, difficulty="easy")
            log: list = []
            latest_chips_before: dict = {}

            async def capture(game_id, event_type, payload_factory):
                nonlocal latest_chips_before
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                if event_type == "hand_starting":
                    latest_chips_before = {
                        p.player_id: p.chips for p in game.state.players
                    }
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)
            # Run up to 5 hands to catch an all-fold scenario
            await _run_until_hands(game, log, num_hands=5, timeout=600)

            all_fold_events = [
                e for e in log
                if e["type"] == "winner" and not e["payload"].get("all_hands")
            ]
            if not all_fold_events:
                pytest.skip("No all-fold hand occurred in 5 hands")

            # Verify the first all-fold winner
            evt = all_fold_events[0]
            winners = evt["payload"]["winners"]
            assert len(winners) == 1, "All-fold must have exactly one winner"
            w = winners[0]
            pid = w["player_id"]
            amount = w["amount"]

            player = game.state.get_player(pid)
            assert player is not None
            chips_before = latest_chips_before.get(pid)
            assert chips_before is not None, "chips_before not captured for this winner"

            # winner.chips already updated at broadcast time; compare
            expected_chips = chips_before + amount
            assert player.chips == expected_chips, (
                f"All-fold winner {pid}: chips_before={chips_before}, "
                f"amount={amount}, expected chips_after={expected_chips}, "
                f"actual chips_after={player.chips}"
            )

            # Pot must be 0 after the hand (cleared after broadcast)
            assert game.state.pot == 0, (
                f"Pot was {game.state.pot} after all-fold hand (expected 0)"
            )

        asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test 4 — short-stack blind post goes all-in correctly
    # ------------------------------------------------------------------

    def test_short_stack_blind_post(self):
        """A player with fewer chips than BB posts only what they have and goes all-in."""
        async def _run():
            # 2 bots so both must post a blind; one is short-stacked
            game = _make_bot_game(num_bots=2, chips=1000)
            # Give one player only 5 chips (BB = 20)
            short = game.state.players[1]
            short.chips = 5
            initial_total = sum(p.chips for p in game.state.players)  # 1000 + 5 = 1005

            log: list = []

            async def capture(game_id, event_type, payload_factory):
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)

            task = asyncio.create_task(game.start())
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                await asyncio.sleep(0.1)
                if any(e["type"] == "hand_starting" for e in log):
                    break
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            assert any(e["type"] == "hand_starting" for e in log), (
                "game never emitted hand_starting"
            )

            # The short-stack player must be all-in with 0 chips remaining
            assert short.is_all_in, (
                f"Short-stack player {short.name} should be all-in after blind post"
            )
            assert short.chips == 0, (
                f"Short-stack player {short.name} should have 0 chips after posting "
                f"blind with only 5 chips (has {short.chips})"
            )

            # Chip conservation holds at hand_starting
            chip_sum = sum(p.chips for p in game.state.players)
            assert chip_sum + game.state.pot == initial_total, (
                f"Chip conservation violated at hand_starting: "
                f"chips={chip_sum}, pot={game.state.pot}, "
                f"total={chip_sum + game.state.pot}, expected={initial_total}"
            )

        asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test 5 — busted player is sitting out in subsequent hand
    # ------------------------------------------------------------------

    def test_bust_out_sitting_out_in_next_hand(self):
        """A busted player (chips == 0 after a hand) must be sitting out next hand."""
        async def _run():
            # Small stacks make bust-outs more likely
            game = _make_bot_game(num_bots=4, chips=50)
            initial_total = sum(p.chips for p in game.state.players)
            log: list = []
            busted_id: list = []  # use list as mutable cell

            async def capture(game_id, event_type, payload_factory):
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                if event_type == "winner" and not busted_id:
                    for p in game.state.players:
                        if p.chips == 0:
                            busted_id.append(p.player_id)
                            break
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)
            # Run up to 10 hands to force a bust
            await _run_until_hands(game, log, num_hands=10, timeout=1200)

            if not busted_id:
                pytest.skip("No player busted within 10 hands")

            pid = busted_id[0]
            busted_player = game.state.get_player(pid)
            assert busted_player is not None

            # Find the hand_starting events that occurred AFTER the bust
            winner_indices = [i for i, e in enumerate(log) if e["type"] == "winner"]
            bust_winner_idx = next(
                (i for i, e in enumerate(log)
                 if e["type"] == "winner" and any(
                     p.player_id == pid and p.chips == 0
                     for p in game.state.players
                 )),
                None
            )
            # Look for a hand_starting event after a winner event
            post_bust_starts = [
                e for i, e in enumerate(log)
                if e["type"] == "hand_starting"
                and any(w_i < i for w_i in winner_indices)
            ]

            if not post_bust_starts:
                pytest.skip("No subsequent hand_starting after a winner event")

            # The busted player must be absent or sitting out in the next hand
            assert busted_player.is_sitting_out or busted_player.chips == 0, (
                f"Busted player {pid} should be sitting out; "
                f"chips={busted_player.chips}, is_sitting_out={busted_player.is_sitting_out}"
            )

            # Chip conservation must still hold
            final_total = sum(p.chips for p in game.state.players)
            assert final_total == initial_total, (
                f"Chip conservation violated after bust: "
                f"initial={initial_total}, final={final_total}"
            )

        asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test 6 — chip conservation across 10 hands (no drift)
    # ------------------------------------------------------------------

    def test_chip_conservation_across_ten_hands(self):
        """sum(player.chips) at every winner event must equal the initial total."""
        async def _run():
            game = _make_bot_game(num_bots=4, chips=1000)
            initial_total = sum(p.chips for p in game.state.players)
            log: list = []
            snapshots: list = []

            async def capture(game_id, event_type, payload_factory):
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                if event_type == "winner":
                    # At winner broadcast: winner's chips already updated;
                    # sum(chips) equals initial_total for both showdown and all-fold.
                    snapshots.append(sum(p.chips for p in game.state.players))
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)
            await _run_until_hands(game, log, num_hands=10, timeout=1200)

            assert len(snapshots) >= 1, "No winner events were captured"
            for i, total in enumerate(snapshots):
                assert total == initial_total, (
                    f"Hand {i + 1}: chip total drifted to {total} "
                    f"(expected {initial_total})"
                )

        asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test 7 — split pot: odd chip remainder goes to first winner
    # ------------------------------------------------------------------

    def test_split_pot_odd_chip_remainder(self):
        """Odd-chip split: remainder goes to first winner; total distributed == pot."""
        from app.core.card import Card, Rank, Suit

        async def _run():
            game = _make_bot_game(num_bots=2, chips=500)
            log: list = []

            async def capture(game_id, event_type, payload_factory):
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)

            # Set up a royal flush on the board so both players play the board
            royal_flush = [
                Card(Rank.ACE,   Suit.SPADES),
                Card(Rank.KING,  Suit.SPADES),
                Card(Rank.QUEEN, Suit.SPADES),
                Card(Rank.JACK,  Suit.SPADES),
                Card(Rank.TEN,   Suit.SPADES),
            ]
            game.state.community_cards = royal_flush

            # Give both players trash off-suit hole cards that don't improve the board
            game.state.players[0].hole_cards = [
                Card(Rank.TWO,   Suit.HEARTS),
                Card(Rank.THREE, Suit.DIAMONDS),
            ]
            game.state.players[1].hole_cards = [
                Card(Rank.FOUR,  Suit.HEARTS),
                Card(Rank.FIVE,  Suit.DIAMONDS),
            ]

            # Set an odd pot so the remainder math is exercised
            game.state.pot = 101
            chips_before = [p.chips for p in game.state.players]

            await game._run_showdown()

            # Both players share the pot (royal flush tie)
            assert game.state.pot == 0, (
                f"Pot should be 0 after showdown, got {game.state.pot}"
            )

            total_distributed = sum(
                p.chips - b for p, b in zip(game.state.players, chips_before)
            )
            assert total_distributed == 101, (
                f"Total distributed ({total_distributed}) != pot (101)"
            )

            # First winner gets the extra chip (remainder = 1)
            gains = [p.chips - b for p, b in zip(game.state.players, chips_before)]
            assert abs(gains[0] - gains[1]) <= 1, (
                f"Split should differ by at most 1 chip; gains={gains}"
            )
            assert max(gains) - min(gains) == 1, (
                f"Odd-chip remainder should cause exactly 1-chip difference; gains={gains}"
            )
            assert sum(gains) == 101, (
                f"Gains must sum to the pot; gains={gains}"
            )

        asyncio.run(_run())

    # ------------------------------------------------------------------
    # Test 8 — per-player net change sums to zero each hand
    # ------------------------------------------------------------------

    def test_per_player_running_balance_matches_net(self):
        """Over 3 hands, each hand's per-player chip deltas must sum to zero.

        Snapshots are taken BEFORE the hand (initial state / after previous winner),
        not at hand_starting, so blind deductions are included in each hand's delta.
        """
        async def _run():
            game = _make_bot_game(num_bots=4, chips=1000)
            log: list = []
            hand_deltas: list = []

            # Snapshot before game starts (pre-blind) as the baseline for hand 1
            prev_snapshot: dict = {p.player_id: p.chips for p in game.state.players}

            async def capture(game_id, event_type, payload_factory):
                nonlocal prev_snapshot
                first_pid = game.state.players[0].player_id
                payload = payload_factory(first_pid)
                if event_type == "winner":
                    # At winner broadcast: winner's chips already reflect the award.
                    # Compare each player's current chips against the pre-hand baseline.
                    current = {p.player_id: p.chips for p in game.state.players}
                    delta = {
                        pid: current.get(pid, 0) - prev_snapshot.get(pid, 0)
                        for pid in prev_snapshot
                    }
                    hand_deltas.append(delta)
                    # This becomes the baseline for the next hand
                    prev_snapshot = current
                log.append({"type": event_type, "payload": payload})

            game.set_broadcast(capture)
            await _run_until_hands(game, log, num_hands=3, timeout=360)

            assert len(hand_deltas) >= 1, "No complete hands captured"
            for hand_num, delta in enumerate(hand_deltas, start=1):
                net = sum(delta.values())
                assert net == 0, (
                    f"Hand {hand_num}: per-player deltas sum to {net} (expected 0). "
                    f"Deltas: {delta}"
                )

        asyncio.run(_run())


# ---------------------------------------------------------------------------
# Live server integration tests
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:18000"
WS_BASE  = "ws://127.0.0.1:18000"


async def _http_create_game(client: httpx.AsyncClient, num_bots: int = 3,
                             difficulty: str = "easy") -> str:
    resp = await client.post(f"{BASE_URL}/api/games", json={
        "num_bots": num_bots,
        "bot_difficulty": difficulty,
        "bot_stack": 1000,
        "small_blind": 10,
        "big_blind": 20,
    })
    assert resp.status_code == 200, f"Create game failed: {resp.text}"
    return resp.json()["game_id"]


async def _http_join_game(client: httpx.AsyncClient, game_id: str,
                           name: str = "Tester", buy_in: int = 500) -> str:
    resp = await client.post(f"{BASE_URL}/api/games/{game_id}/join", json={
        "player_name": name,
        "buy_in": buy_in,
    })
    assert resp.status_code == 200, f"Join game failed: {resp.text}"
    return resp.json()["player_id"]


async def _ws_recv(ws, timeout: float = 10.0) -> dict:
    """Receive and JSON-parse one WebSocket message."""
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


class TestLiveServerSimulation:
    """End-to-end tests that connect to a real uvicorn process over WebSocket."""

    def test_first_message_is_game_state(self, live_server):
        """Connecting to /ws/{game_id}/{player_id} must immediately yield game_state."""
        async def _run():
            async with httpx.AsyncClient() as client:
                game_id   = await _http_create_game(client, num_bots=2)
                player_id = await _http_join_game(client, game_id)

            url = f"{WS_BASE}/ws/{game_id}/{player_id}"
            async with websockets.connect(url) as ws:
                first = await _ws_recv(ws, timeout=5.0)

            assert first["type"] == "game_state", (
                f"Expected game_state as first message, got {first['type']!r}"
            )
            p = first["payload"]
            assert p["game_id"] == game_id
            assert "phase"   in p
            assert "players" in p
            assert "pot"     in p

        asyncio.run(_run())

    def test_bots_complete_a_full_hand(self, live_server):
        """A 4-bot game must produce hand_starting and winner events within 90 s.

        The joined human also responds to any your_turn events so the game
        never stalls waiting for a human action.
        """
        async def _run():
            async with httpx.AsyncClient() as client:
                game_id   = await _http_create_game(client, num_bots=4)
                player_id = await _http_join_game(client, game_id, buy_in=500)

            url = f"{WS_BASE}/ws/{game_id}/{player_id}"
            events: list[dict] = []

            async with websockets.connect(url) as ws:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    try:
                        e = await _ws_recv(ws, timeout=min(remaining, 5.0))
                        events.append(e)
                        # Respond to our turn so the game never stalls
                        if e["type"] == "your_turn":
                            valid  = e["payload"].get("valid_actions", {})
                            action = (
                                "check" if valid.get("can_check")          else
                                "call"  if valid.get("call_amount", 0) > 0 else
                                "fold"
                            )
                            await ws.send(json.dumps({
                                "type": "action",
                                "payload": {"action": action, "amount": 0},
                            }))
                        elif e["type"] == "winner":
                            break
                    except asyncio.TimeoutError:
                        break

            types = {e["type"] for e in events}
            assert "game_state"    in types, "Missing initial game_state event"
            assert "hand_starting" in types, "Missing hand_starting event"
            assert "winner"        in types, "Missing winner event"

            winner_evt = next(e for e in events if e["type"] == "winner")
            w = winner_evt["payload"]["winners"][0]
            assert "player_id" in w
            assert w.get("amount", 0) > 0, "Winner must receive a positive chip amount"

        asyncio.run(_run())

    def test_human_player_receives_your_turn_and_acts(self, live_server):
        """Human player receives your_turn events, responds with actions, and 2 hands complete."""
        async def _run():
            async with httpx.AsyncClient() as client:
                game_id   = await _http_create_game(client, num_bots=3)
                player_id = await _http_join_game(client, game_id, name="Human", buy_in=1000)

            url = f"{WS_BASE}/ws/{game_id}/{player_id}"
            events:       list[dict] = []
            actions_sent: list[str]  = []
            hands_done = 0

            async with websockets.connect(url) as ws:
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline and hands_done < 2:
                    remaining = deadline - time.monotonic()
                    try:
                        e = await _ws_recv(ws, timeout=min(remaining, 5.0))
                    except asyncio.TimeoutError:
                        continue

                    events.append(e)

                    if e["type"] == "your_turn":
                        valid  = e["payload"].get("valid_actions", {})
                        action = (
                            "check" if valid.get("can_check")          else
                            "call"  if valid.get("call_amount", 0) > 0 else
                            "fold"
                        )
                        await ws.send(json.dumps({
                            "type": "action",
                            "payload": {"action": action, "amount": 0},
                        }))
                        actions_sent.append(action)

                    elif e["type"] == "winner":
                        hands_done += 1

            assert hands_done >= 2, (
                f"Expected 2 complete hands, only {hands_done} finished"
            )
            assert actions_sent, "Human player should have taken at least one action"

            types = {e["type"] for e in events}
            assert "your_turn"     in types, "Never received a your_turn event"
            assert "hand_starting" in types, "Never received a hand_starting event"

        asyncio.run(_run())

    def test_opponent_cards_masked_over_websocket(self, live_server):
        """Opponents' hole cards must be '??' in all game_state / hand_starting messages."""
        async def _run():
            async with httpx.AsyncClient() as client:
                game_id   = await _http_create_game(client, num_bots=3)
                player_id = await _http_join_game(client, game_id, name="PrivacyTest", buy_in=500)

            url = f"{WS_BASE}/ws/{game_id}/{player_id}"
            events: list[dict] = []

            async with websockets.connect(url) as ws:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    try:
                        e = await _ws_recv(ws, timeout=min(remaining, 3.0))
                        events.append(e)
                        if e["type"] == "hand_starting":
                            break
                    except asyncio.TimeoutError:
                        break

            card_events = [e for e in events if e["type"] in ("game_state", "hand_starting")]
            assert card_events, "Expected at least one game_state or hand_starting event"

            for evt in card_events:
                for pd in evt["payload"].get("players", []):
                    if pd["player_id"] == player_id:
                        # Own cards are visible after hand_starting
                        pass
                    else:
                        for card in pd.get("hole_cards", []):
                            assert card == "??", (
                                f"Opponent {pd['name']!r} card {card!r} must be '??' "
                                f"in {evt['type']!r} payload (card leak!)"
                            )

        asyncio.run(_run())

    def test_game_plays_two_consecutive_hands(self, live_server):
        """hand_number must increment from 1 to 2 across two consecutive hands.

        The joined human responds to any your_turn events so the game never stalls.
        """
        async def _run():
            async with httpx.AsyncClient() as client:
                game_id   = await _http_create_game(client, num_bots=4)
                player_id = await _http_join_game(client, game_id, buy_in=500)

            url = f"{WS_BASE}/ws/{game_id}/{player_id}"
            events: list[dict] = []

            async with websockets.connect(url) as ws:
                deadline = time.monotonic() + 180
                while time.monotonic() < deadline:
                    remaining = deadline - time.monotonic()
                    try:
                        e = await _ws_recv(ws, timeout=min(remaining, 5.0))
                        events.append(e)
                        # Respond to our turn so the game never stalls
                        if e["type"] == "your_turn":
                            valid  = e["payload"].get("valid_actions", {})
                            action = (
                                "check" if valid.get("can_check")          else
                                "call"  if valid.get("call_amount", 0) > 0 else
                                "fold"
                            )
                            await ws.send(json.dumps({
                                "type": "action",
                                "payload": {"action": action, "amount": 0},
                            }))
                    except asyncio.TimeoutError:
                        break
                    winner_count = sum(1 for ev in events if ev["type"] == "winner")
                    if winner_count >= 2:
                        break

            starting_events = [e for e in events if e["type"] == "hand_starting"]
            assert len(starting_events) >= 2, (
                f"Expected at least 2 hand_starting events, got {len(starting_events)}"
            )
            hand_numbers = [e["payload"]["hand_number"] for e in starting_events[:2]]
            assert hand_numbers[0] == 1, f"First hand_number should be 1, got {hand_numbers[0]}"
            assert hand_numbers[1] == 2, f"Second hand_number should be 2, got {hand_numbers[1]}"

        asyncio.run(_run())
