"""
PokerGame — the central async orchestrator for a Texas Hold'em game.

State machine:
  WAITING → STARTING → PREFLOP → FLOP → TURN → RIVER → SHOWDOWN → HAND_OVER → (loop)
"""
from __future__ import annotations
import asyncio
import logging
import random
import uuid
from typing import Any, Callable, Dict, List, Optional

from app.core.card import Deck
from app.core.hand_evaluator import eval_best, rank_to_class, rank_to_string
from app.core.pot import PotManager
from app.game.betting import BettingAction, BettingResult, BettingRound
from app.game.game_state import GamePhase, GameState, GameVariant, PlayerState
from app.game.player import Player
from app.game.rules import (
    advance_dealer,
    first_to_act_postflop,
    first_to_act_preflop,
    get_blind_indices,
    next_active_seat,
    post_blinds,
)

logger = logging.getLogger(__name__)


class PokerGame:
    """
    Manages a complete Texas Hold'em game session.

    Broadcast callback receives (game_id, event_type, payload_factory).
    payload_factory is a callable(player_id) → dict so each player can
    receive a personalized payload (hiding opponents' hole cards).
    """

    def __init__(
        self,
        game_id: str,
        variant: GameVariant,
        small_blind: int,
        big_blind: int,
        max_players: int = 9,
        min_buy_in: Optional[int] = None,
        max_buy_in: Optional[int] = None,
    ) -> None:
        self.state = GameState(
            game_id=game_id,
            variant=variant,
            small_blind=small_blind,
            big_blind=big_blind,
            max_players=max_players,
            min_buy_in=min_buy_in or big_blind * 20,
            max_buy_in=max_buy_in or big_blind * 200,
        )
        self._players: Dict[str, Player] = {}
        self._pot_manager = PotManager()
        self._deck = Deck()
        self._broadcast_cb: Optional[Callable] = None
        self._current_betting: Optional[BettingRound] = None
        self._hand_task: Optional[asyncio.Task] = None
        self._action_event = asyncio.Event()
        self._pending_action: Optional[tuple[str, BettingAction, int]] = None

    # ------------------------------------------------------------------
    # Player management
    # ------------------------------------------------------------------

    def add_player(self, player: Player) -> bool:
        """Add a player to the game. Returns False if seat unavailable."""
        if len(self._players) >= self.state.max_players:
            return False
        if player.player_id in self._players:
            return False
        self._players[player.player_id] = player
        ps = PlayerState(
            player_id=player.player_id,
            name=player.name,
            chips=player.chips,
            is_bot=player.is_bot,
            seat=len(self.state.players),
        )
        self.state.players.append(ps)
        return True

    def remove_player(self, player_id: str) -> None:
        """Remove a player (mark sitting out if mid-hand)."""
        if player_id not in self._players:
            return
        ps = self.state.get_player(player_id)
        if ps:
            if self.state.phase not in (GamePhase.WAITING, GamePhase.HAND_OVER):
                ps.is_sitting_out = True
                ps.is_folded = True
            else:
                self.state.players = [p for p in self.state.players if p.player_id != player_id]
        del self._players[player_id]

    def set_broadcast(self, cb: Callable) -> None:
        """Set broadcast callback: cb(game_id, event_type, payload_factory)."""
        self._broadcast_cb = cb

    # ------------------------------------------------------------------
    # Action submission
    # ------------------------------------------------------------------

    async def submit_action(self, player_id: str, action: BettingAction, amount: int = 0) -> None:
        """Called externally (WebSocket handler) to submit a player action."""
        self._pending_action = (player_id, action, amount)
        self._action_event.set()

    # ------------------------------------------------------------------
    # Hand lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the game loop."""
        self.state.phase = GamePhase.WAITING
        await self._broadcast("game_state", self._state_payload_factory)
        self._hand_task = asyncio.create_task(self._game_loop())

    async def _game_loop(self) -> None:
        """Main game loop — runs hands until the game ends."""
        while True:
            # Wait for enough players
            while len(self.state.seated_players) < 2:
                await asyncio.sleep(1)

            self.state.phase = GamePhase.STARTING
            await asyncio.sleep(1)
            await self._run_hand()

            # Mark busted players immediately after each hand
            for p in self.state.players:
                if p.chips == 0 and not p.is_sitting_out:
                    p.is_sitting_out = True

            self.state.phase = GamePhase.HAND_OVER
            await self._broadcast("hand_over", self._state_payload_factory)
            await asyncio.sleep(3)

            # End the game when only one player has chips
            if len(self.state.seated_players) < 2:
                remaining = self.state.seated_players
                winner = remaining[0] if remaining else None
                winner_payload = {
                    "winner_name": winner.name if winner else "",
                    "winner_chips": winner.chips if winner else 0,
                }
                await self._broadcast("game_over", lambda pid: winner_payload)
                break

    async def _run_hand(self) -> None:
        """Run a single hand from deal to showdown."""
        self.state.hand_number += 1

        # Reset hand state
        self._pot_manager.reset()
        for p in self.state.players:
            p.hole_cards = []
            p.bet = 0
            p.total_bet = 0
            p.is_folded = False
            p.is_all_in = False

        # Advance dealer
        advance_dealer(self.state)
        sb_idx, bb_idx = get_blind_indices(self.state)
        sb_amount, bb_amount = post_blinds(self.state)

        # Sync pot manager
        sb_player = self.state.players[sb_idx]
        bb_player = self.state.players[bb_idx]
        self._pot_manager.add_contribution(sb_player.player_id, sb_amount,
                                           sb_player.is_all_in)
        self._pot_manager.add_contribution(bb_player.player_id, bb_amount,
                                           bb_player.is_all_in)

        # Deal hole cards
        self._deck.reset()
        for _ in range(2):
            for p in self.state.active_players:
                card = self._deck.deal_one()
                p.hole_cards.append(card)

        self.state.phase = GamePhase.PREFLOP
        self.state.community_cards = []

        await self._broadcast("hand_starting", self._state_payload_factory)

        # Preflop betting
        first = first_to_act_preflop(self.state)
        self.state.current_player_index = first
        result = await self._run_betting_round(GamePhase.PREFLOP)
        if result == BettingResult.ALL_FOLDED:
            await self._award_to_last_remaining()
            return

        # FLOP — brief pause so clients can see the last action
        await asyncio.sleep(1.5)
        self.state.phase = GamePhase.FLOP
        for card in self._deck.deal(3):
            self.state.community_cards.append(card)
        await self._broadcast("community_card", self._state_payload_factory)
        first = first_to_act_postflop(self.state)
        self.state.current_player_index = first
        self._reset_street_bets()
        result = await self._run_betting_round(GamePhase.FLOP)
        if result == BettingResult.ALL_FOLDED:
            await self._award_to_last_remaining()
            return

        # TURN
        await asyncio.sleep(1.5)
        self.state.phase = GamePhase.TURN
        self.state.community_cards.append(self._deck.deal_one())
        await self._broadcast("community_card", self._state_payload_factory)
        first = first_to_act_postflop(self.state)
        self.state.current_player_index = first
        self._reset_street_bets()
        result = await self._run_betting_round(GamePhase.TURN)
        if result == BettingResult.ALL_FOLDED:
            await self._award_to_last_remaining()
            return

        # RIVER
        await asyncio.sleep(1.5)
        self.state.phase = GamePhase.RIVER
        self.state.community_cards.append(self._deck.deal_one())
        await self._broadcast("community_card", self._state_payload_factory)
        first = first_to_act_postflop(self.state)
        self.state.current_player_index = first
        self._reset_street_bets()
        result = await self._run_betting_round(GamePhase.RIVER)
        if result == BettingResult.ALL_FOLDED:
            await self._award_to_last_remaining()
            return

        # Showdown
        await asyncio.sleep(1.5)
        self.state.phase = GamePhase.SHOWDOWN
        await self._run_showdown()

    def _reset_street_bets(self) -> None:
        for p in self.state.players:
            p.bet = 0

    async def _run_betting_round(self, phase: GamePhase) -> BettingResult:
        """Run a full betting round. Returns why it ended."""
        start_idx = self.state.current_player_index
        betting = BettingRound(self.state, start_idx, phase)
        self._current_betting = betting

        # Notify whose turn it is
        current_pid = betting.next_to_act()
        if current_pid is None:
            return BettingResult.ROUND_COMPLETE

        await self._prompt_player(current_pid, betting)

        while True:
            # Wait for action
            action_pid, action, amount = await self._wait_for_action(current_pid)

            # Track contribution before the action to compute delta
            prev_contribution = self._pot_manager.get_contribution(action_pid)
            result = betting.apply_action(action_pid, action, amount)

            # Sync pot manager with actual chips added
            ps = self.state.get_player(action_pid)
            if ps:
                new_contribution = ps.total_bet
                delta = new_contribution - prev_contribution
                if delta > 0:
                    self._pot_manager.add_contribution(action_pid, delta, ps.is_all_in)

            action_player_name = self._players[action_pid].name if action_pid in self._players else action_pid
            await self._broadcast("action_taken", lambda pid, _ap=action_pid, _an=action_player_name, _a=action, _amt=amount: {
                "player_id": _ap,
                "name": _an,
                "action": _a.value,
                "amount": _amt,
                "pot": self.state.pot,
            })

            if result != BettingResult.CONTINUE:
                self._current_betting = None
                return result

            # Next player
            current_pid = betting.next_to_act()
            if current_pid is None:
                self._current_betting = None
                return BettingResult.ROUND_COMPLETE

            await self._prompt_player(current_pid, betting)

    async def _wait_for_action(self, expected_player_id: str) -> tuple[str, BettingAction, int]:
        """
        Wait for an action from expected_player_id.
        If it's a bot, schedule the bot action and wait for it.
        """
        player = self._players.get(expected_player_id)
        if player and player.is_bot:
            # Schedule bot action
            asyncio.create_task(self._schedule_bot_action(expected_player_id))

        # Wait for action event
        while True:
            self._action_event.clear()
            await self._action_event.wait()
            if self._pending_action and self._pending_action[0] == expected_player_id:
                action = self._pending_action
                self._pending_action = None
                return action

    async def _schedule_bot_action(self, player_id: str) -> None:
        """Schedule a bot action after a short delay."""
        await asyncio.sleep(random.uniform(0.5, 2.0))
        try:
            from app.ai.bot import BotPlayer
            bot = BotPlayer(player_id)
            ps = self.state.get_player(player_id)
            player_obj = self._players.get(player_id)
            difficulty = "medium"
            if player_obj:
                difficulty = player_obj.bot_difficulty or "medium"
            if self._current_betting and ps:
                valid = self._current_betting.get_valid_actions(player_id)
                action, amount = bot.decide(self.state, ps, valid, difficulty)
                await self.submit_action(player_id, action, amount)
        except Exception as e:
            logger.error(f"Bot action error for {player_id}: {e}")
            # Fallback: fold
            await self.submit_action(player_id, BettingAction.FOLD)

    async def _prompt_player(self, player_id: str, betting: BettingRound) -> None:
        """Send a 'your_turn' event with valid actions."""
        valid = betting.get_valid_actions(player_id)

        def factory(pid: str, _vid=player_id, _v=valid) -> Optional[dict]:
            if pid != _vid:
                return None  # not their turn
            return {
                "player_id": _vid,
                "valid_actions": {
                    "can_check": _v.can_check,
                    "call_amount": _v.call_amount,
                    "min_raise": _v.min_raise,
                    "max_raise": _v.max_raise,
                    "can_raise": _v.can_raise,
                },
            }

        await self._broadcast("your_turn", factory)

    # ------------------------------------------------------------------
    # Showdown & award
    # ------------------------------------------------------------------

    async def _run_showdown(self) -> None:
        """Evaluate hands, compute winners, award pots."""
        active = self.state.active_players

        # Build per-player hand scores
        scores: Dict[str, int] = {}
        for p in active:
            all_cards = p.hole_cards + self.state.community_cards
            scores[p.player_id] = eval_best(all_cards)

        # Calculate side pots
        active_ids = [p.player_id for p in active]
        side_pots = self._pot_manager.calculate_side_pots(active_ids)

        if not side_pots:
            # Fallback: single pot
            from app.core.pot import SidePot
            side_pots = [SidePot(
                amount=self.state.pot,
                eligible_player_ids=active_ids,
            )]

        winners_info: List[dict] = []

        for pot in side_pots:
            eligible = [p for p in active if p.player_id in pot.eligible_player_ids]
            if not eligible:
                continue

            best_score = min(scores[p.player_id] for p in eligible)
            pot_winners = [p for p in eligible if scores[p.player_id] == best_score]

            # Split the pot evenly (remainder goes to first winner)
            share = pot.amount // len(pot_winners)
            remainder = pot.amount % len(pot_winners)

            for i, winner in enumerate(pot_winners):
                award = share + (remainder if i == 0 else 0)
                winner.chips += award
                # Sync back to Player object
                if winner.player_id in self._players:
                    self._players[winner.player_id].chips = winner.chips

                hand_name = rank_to_string(best_score)
                winners_info.append({
                    "player_id": winner.player_id,
                    "name": winner.name,
                    "amount": award,
                    "hand": hand_name,
                    "hole_cards": [str(c) for c in winner.hole_cards],
                })

        self.state.pot = 0

        await self._broadcast("winner", lambda pid, _wi=winners_info: {
            "winners": _wi,
            "community_cards": [str(c) for c in self.state.community_cards],
            "all_hands": {
                p.player_id: {
                    "name": p.name,
                    "hole_cards": [str(c) for c in p.hole_cards],
                    "score": scores.get(p.player_id, 9999),
                    "hand_name": rank_to_string(scores.get(p.player_id, 9999)),
                }
                for p in active
            },
        })

    async def _award_to_last_remaining(self) -> None:
        """Award pot to the only non-folded player."""
        active = self.state.active_players
        if len(active) == 1:
            winner = active[0]
            winner.chips += self.state.pot
            if winner.player_id in self._players:
                self._players[winner.player_id].chips = winner.chips

            await self._broadcast("winner", lambda pid, _w=winner, _pot=self.state.pot: {
                "winners": [{"player_id": _w.player_id, "name": _w.name, "amount": _pot, "hand": "Last player standing"}],
                "community_cards": [str(c) for c in self.state.community_cards],
                "all_hands": {},
            })
            self.state.pot = 0

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def _broadcast(self, event_type: str, payload_factory: Callable) -> None:
        """Send an event to all players via the broadcast callback."""
        if self._broadcast_cb:
            await self._broadcast_cb(self.state.game_id, event_type, payload_factory)

    def _state_payload_factory(self, player_id: str) -> dict:
        """Build a game_state payload personalized for player_id."""
        state = self.state
        players_payload = []
        for p in state.players:
            pd: dict = {
                "player_id": p.player_id,
                "name": p.name,
                "chips": p.chips,
                "bet": p.bet,
                "total_bet": p.total_bet,
                "is_folded": p.is_folded,
                "is_all_in": p.is_all_in,
                "is_bot": p.is_bot,
                "seat": p.seat,
                "is_active": (p.player_id == state.current_player.player_id
                              if state.current_player else False),
            }
            # Only reveal hole cards to the owning player.
            # Opponent cards at showdown are revealed via the 'winner' event,
            # not via game_state snapshots — this prevents a race condition
            # where a player connecting during SHOWDOWN phase would see all cards.
            if p.player_id == player_id:
                pd["hole_cards"] = [str(c) for c in p.hole_cards]
            else:
                pd["hole_cards"] = ["??" for _ in p.hole_cards]
            players_payload.append(pd)

        return {
            "game_id": state.game_id,
            "phase": state.phase.value,
            "variant": state.variant.value,
            "players": players_payload,
            "community_cards": [str(c) for c in state.community_cards],
            "pot": state.pot,
            "hand_number": state.hand_number,
            "dealer_index": state.dealer_index,
            "current_player_index": state.current_player_index,
            "small_blind": state.small_blind,
            "big_blind": state.big_blind,
        }

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    def get_state_for_player(self, player_id: str) -> dict:
        return self._state_payload_factory(player_id)


# ---------------------------------------------------------------------------
# Headless test runner
# ---------------------------------------------------------------------------

async def _run_test_hand_async() -> None:
    from app.game.player import Player

    game = PokerGame(
        game_id="test-001",
        variant=GameVariant.NO_LIMIT,
        small_blind=10,
        big_blind=20,
        max_players=6,
    )

    for i in range(4):
        p = Player(
            player_id=f"bot-{i}",
            name=f"Bot {i+1}",
            chips=1000,
            is_bot=True,
            bot_difficulty="medium",
        )
        game.add_player(p)

    events: list = []

    async def broadcast(game_id, event_type, payload_factory):
        for p in game.state.players:
            payload = payload_factory(p.player_id)
            events.append((event_type, p.player_id, payload))
        print(f"  [{event_type}] phase={game.state.phase.value} pot={game.state.pot}")

    game.set_broadcast(broadcast)

    print("Starting test hand...")
    await game.start()
    # Run for a bit then cancel
    await asyncio.sleep(15)

    print(f"\nHand complete. Events captured: {len(events)}")
    print(f"Player chips: {[(p.name, p.chips) for p in game.state.players]}")


def run_test_hand() -> None:
    asyncio.run(_run_test_hand_async())


if __name__ == "__main__":
    run_test_hand()
