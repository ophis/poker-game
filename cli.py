#!/usr/bin/env python3
"""
CLI for testing the poker game engine without the GUI.

Usage:
    python cli.py                        # 1 human + 3 medium bots, NLHE 10/20
    python cli.py --bots 5               # 1 human + 5 bots
    python cli.py --bots 2 --difficulty hard
    python cli.py --variant fixed_limit
    python cli.py --blinds 25 50 --stack 5000
    python cli.py --watch                # all bots, no human (spectator mode)
    python cli.py --hands 10             # play 10 hands then stop
"""
from __future__ import annotations

import argparse
import sys
from itertools import combinations
from typing import List, Optional, Tuple

from app.core.card import Card, Deck, Rank, Suit
from app.core.hand_evaluator import eval_best, rank_to_class, rank_to_string, HandClass
from app.core.pot import PotManager
from app.game.betting import BettingAction, BettingResult, BettingRound, ValidActions
from app.game.game_state import GamePhase, GameState, GameVariant, PlayerState
from app.game.rules import (
    advance_dealer,
    first_to_act_postflop,
    first_to_act_preflop,
    get_blind_indices,
    next_active_seat,
    post_blinds,
)
from app.ai.bot import BotPlayer


# -- ANSI colors ---------------------------------------------------------------

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"

SUIT_SYMBOLS = {"c": "\u2663", "d": "\u2666", "h": "\u2665", "s": "\u2660"}
SUIT_COLORS  = {"c": GREEN, "d": BLUE, "h": RED, "s": WHITE}


def fmt_card(card_str: str) -> str:
    """Pretty-print a card like 'Ah' → colored 'A♥'."""
    if not card_str or card_str == "??":
        return f"{DIM}[??]{RESET}"
    rank = card_str[:-1]
    suit_ch = card_str[-1]
    sym = SUIT_SYMBOLS.get(suit_ch, suit_ch)
    clr = SUIT_COLORS.get(suit_ch, "")
    return f"{clr}{BOLD}{rank}{sym}{RESET}"


def fmt_cards(cards: List[str]) -> str:
    return " ".join(fmt_card(c) for c in cards)


def fmt_chips(n: int) -> str:
    return f"{YELLOW}${n:,}{RESET}"


# -- Display helpers -----------------------------------------------------------

def print_divider(label: str = "") -> None:
    if label:
        print(f"\n{DIM}{'─' * 20} {BOLD}{WHITE}{label} {DIM}{'─' * 20}{RESET}")
    else:
        print(f"{DIM}{'─' * 60}{RESET}")


def print_table(state: GameState, human_id: Optional[str] = None) -> None:
    """Print the full table state."""
    # Community cards
    if state.community_cards:
        board = fmt_cards([str(c) for c in state.community_cards])
        print(f"\n  Board: {board}")
    else:
        print(f"\n  Board: {DIM}(no community cards yet){RESET}")

    print(f"  Pot:   {fmt_chips(state.pot)}")
    print()

    # Players
    for i, p in enumerate(state.players):
        marker_parts = []
        if i == state.dealer_index:
            marker_parts.append(f"{YELLOW}D{RESET}")
        if p.is_folded:
            marker_parts.append(f"{DIM}folded{RESET}")
        if p.is_all_in:
            marker_parts.append(f"{RED}{BOLD}ALL-IN{RESET}")
        if p.is_sitting_out:
            marker_parts.append(f"{DIM}sitting out{RESET}")
        markers = f" ({', '.join(marker_parts)})" if marker_parts else ""

        # Show hole cards: always for human, hide for bots unless showdown/folded
        if p.hole_cards and (p.player_id == human_id or state.phase == GamePhase.SHOWDOWN):
            cards = fmt_cards([str(c) for c in p.hole_cards])
        elif p.hole_cards:
            cards = fmt_cards(["??" for _ in p.hole_cards])
        else:
            cards = ""

        bet_str = f"  bet {fmt_chips(p.bet)}" if p.bet > 0 else ""
        active = f"{CYAN}>{RESET} " if i == state.current_player_index else "  "

        print(f"  {active}{p.name:<12} {fmt_chips(p.chips):>18}  {cards}{bet_str}{markers}")

    print()


def print_hand_result(
    state: GameState,
    winners: List[dict],
    scores: dict,
    human_id: Optional[str],
) -> None:
    """Print showdown results."""
    # Show all hands
    active = [p for p in state.players if not p.is_folded and not p.is_sitting_out]
    if len(active) > 1 and scores:
        print_divider("SHOWDOWN")
        for p in active:
            cards = fmt_cards([str(c) for c in p.hole_cards])
            sc = scores.get(p.player_id, 9999)
            hand_name = rank_to_string(sc)
            print(f"  {p.name:<12} {cards}  {CYAN}{hand_name}{RESET}")
        print()

    # Winners
    for w in winners:
        name = w.get("name", w["player_id"])
        print(f"  {GREEN}{BOLD}{name} wins {fmt_chips(w['amount'])}{RESET}  ({w['hand']})")
    print()


def describe_hand(hole_cards: List[Card], community: List[Card]) -> str:
    """Describe the best hand the human currently holds."""
    all_cards = hole_cards + community
    if len(all_cards) < 5:
        return ""
    score = eval_best(all_cards)
    return rank_to_string(score)


# -- Input helpers -------------------------------------------------------------

def prompt_action(valid: ValidActions, state: GameState, player: PlayerState) -> Tuple[BettingAction, int]:
    """Prompt the human player for their action."""
    hand_desc = describe_hand(player.hole_cards, state.community_cards)
    if hand_desc:
        print(f"  Your hand: {CYAN}{hand_desc}{RESET}")

    options = [f"  {RED}[f]{RESET} Fold"]
    if valid.can_check:
        options.append(f"  {GREEN}[c]{RESET} Check")
    else:
        options.append(f"  {BLUE}[c]{RESET} Call {fmt_chips(valid.call_amount)}")
    if valid.can_raise:
        if state.variant == GameVariant.FIXED_LIMIT:
            options.append(f"  {YELLOW}[r]{RESET} Raise to {fmt_chips(valid.min_raise)}")
        else:
            options.append(
                f"  {YELLOW}[r]{RESET} Raise ({fmt_chips(valid.min_raise)}–{fmt_chips(valid.max_raise)})"
            )
    options.append(f"  {RED}{BOLD}[a]{RESET} All-in ({fmt_chips(valid.player_stack + player.bet)})")
    print("\n".join(options))

    while True:
        try:
            raw = input(f"\n  {BOLD}Your action: {RESET}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if raw in ("f", "fold"):
            return BettingAction.FOLD, 0
        elif raw in ("c", "call", "check"):
            if valid.can_check:
                return BettingAction.CHECK, 0
            else:
                return BettingAction.CALL, valid.call_amount
        elif raw in ("a", "allin", "all-in", "all_in"):
            return BettingAction.ALL_IN, 0
        elif raw.startswith("r") or raw.startswith("raise"):
            if not valid.can_raise:
                print(f"  {RED}Cannot raise.{RESET}")
                continue
            if state.variant == GameVariant.FIXED_LIMIT:
                return BettingAction.RAISE, valid.min_raise
            parts = raw.split()
            if len(parts) >= 2:
                try:
                    amount = int(parts[1])
                except ValueError:
                    print(f"  {RED}Invalid amount.{RESET}")
                    continue
            else:
                try:
                    amount = int(input(f"  Raise to ({valid.min_raise}–{valid.max_raise}): "))
                except (ValueError, EOFError, KeyboardInterrupt):
                    print()
                    continue
            if amount < valid.min_raise:
                amount = valid.min_raise
            if amount > valid.max_raise:
                amount = valid.max_raise
            return BettingAction.RAISE, amount
        else:
            print(f"  {DIM}Enter f/c/r/a (or 'r 150' to raise to 150){RESET}")


# -- Synchronous game driver ---------------------------------------------------

class CLIGame:
    """Drive the poker engine synchronously from the terminal."""

    def __init__(
        self,
        num_bots: int = 3,
        difficulty: str = "medium",
        variant: str = "no_limit",
        small_blind: int = 10,
        big_blind: int = 20,
        stack: int = 1000,
        watch: bool = False,
        max_hands: int = 0,
    ) -> None:
        self.variant = GameVariant.NO_LIMIT if variant == "no_limit" else GameVariant.FIXED_LIMIT
        self.state = GameState(
            game_id="cli",
            variant=self.variant,
            small_blind=small_blind,
            big_blind=big_blind,
            max_players=num_bots + (0 if watch else 1),
        )
        self.pot_manager = PotManager()
        self.deck = Deck()
        self.watch = watch
        self.max_hands = max_hands
        self.difficulty = difficulty
        self.human_id: Optional[str] = None

        # Add human player
        if not watch:
            self.human_id = "human"
            self.state.players.append(PlayerState(
                player_id="human",
                name="You",
                chips=stack,
                is_bot=False,
                seat=0,
            ))

        # Add bots
        for i in range(num_bots):
            self.state.players.append(PlayerState(
                player_id=f"bot-{i}",
                name=f"Bot {i + 1}",
                chips=stack,
                is_bot=True,
                seat=len(self.state.players),
            ))

    def run(self) -> None:
        print(f"\n{BOLD}{'=' * 60}{RESET}")
        variant_name = "No-Limit" if self.variant == GameVariant.NO_LIMIT else "Fixed-Limit"
        print(f"{BOLD}  Texas Hold'em — {variant_name}  "
              f"({self.state.small_blind}/{self.state.big_blind}){RESET}")
        print(f"  {len(self.state.players)} players, "
              f"{fmt_chips(self.state.players[0].chips)} starting stack")
        if self.max_hands:
            print(f"  Playing {self.max_hands} hand(s)")
        print(f"{BOLD}{'=' * 60}{RESET}")

        hand = 0
        while True:
            # Remove busted players
            seated = [p for p in self.state.players if not p.is_sitting_out]
            if len(seated) < 2:
                print(f"\n{BOLD}Game over — not enough players.{RESET}")
                break

            # Check if human busted
            if self.human_id:
                human = self.state.get_player(self.human_id)
                if human and human.chips == 0:
                    print(f"\n{RED}{BOLD}You're out of chips! Game over.{RESET}")
                    break

            hand += 1
            if self.max_hands and hand > self.max_hands:
                break

            self._play_hand(hand)

        # Final standings
        print_divider("FINAL STANDINGS")
        standings = sorted(self.state.players, key=lambda p: p.chips, reverse=True)
        for i, p in enumerate(standings):
            marker = " (busted)" if p.chips == 0 else ""
            print(f"  {i + 1}. {p.name:<12} {fmt_chips(p.chips)}{marker}")
        print()

    def _play_hand(self, hand_num: int) -> None:
        state = self.state
        state.hand_number = hand_num

        # Reset
        self.pot_manager.reset()
        for p in state.players:
            p.hole_cards = []
            p.bet = 0
            p.total_bet = 0
            p.is_folded = False
            p.is_all_in = False
        for p in state.players:
            if p.chips == 0 and not p.is_sitting_out:
                p.is_sitting_out = True

        # Advance dealer + post blinds
        advance_dealer(state)
        sb_idx, bb_idx = get_blind_indices(state)
        sb_amt, bb_amt = post_blinds(state)

        sb = state.players[sb_idx]
        bb = state.players[bb_idx]
        self.pot_manager.add_contribution(sb.player_id, sb_amt, sb.is_all_in)
        self.pot_manager.add_contribution(bb.player_id, bb_amt, bb.is_all_in)

        # Deal
        self.deck.reset()
        for _ in range(2):
            for p in state.active_players:
                p.hole_cards.append(self.deck.deal_one())

        state.phase = GamePhase.PREFLOP
        state.community_cards = []

        print_divider(f"HAND #{hand_num}")
        print(f"  Dealer: {state.players[state.dealer_index].name}  |  "
              f"SB: {sb.name} ({fmt_chips(sb_amt)})  |  "
              f"BB: {bb.name} ({fmt_chips(bb_amt)})")
        print_table(state, self.human_id)

        # --- Preflop ---
        first = first_to_act_preflop(state)
        state.current_player_index = first
        result = self._run_street("PREFLOP")
        if result == BettingResult.ALL_FOLDED:
            self._award_last()
            return

        # --- Flop ---
        state.phase = GamePhase.FLOP
        for c in self.deck.deal(3):
            state.community_cards.append(c)
        self._reset_bets()
        state.current_player_index = first_to_act_postflop(state)
        print_divider("FLOP")
        print_table(state, self.human_id)
        result = self._run_street("FLOP")
        if result == BettingResult.ALL_FOLDED:
            self._award_last()
            return

        # --- Turn ---
        state.phase = GamePhase.TURN
        state.community_cards.append(self.deck.deal_one())
        self._reset_bets()
        state.current_player_index = first_to_act_postflop(state)
        print_divider("TURN")
        print_table(state, self.human_id)
        result = self._run_street("TURN")
        if result == BettingResult.ALL_FOLDED:
            self._award_last()
            return

        # --- River ---
        state.phase = GamePhase.RIVER
        state.community_cards.append(self.deck.deal_one())
        self._reset_bets()
        state.current_player_index = first_to_act_postflop(state)
        print_divider("RIVER")
        print_table(state, self.human_id)
        result = self._run_street("RIVER")
        if result == BettingResult.ALL_FOLDED:
            self._award_last()
            return

        # --- Showdown ---
        state.phase = GamePhase.SHOWDOWN
        self._showdown()

    def _reset_bets(self) -> None:
        for p in self.state.players:
            p.bet = 0

    def _run_street(self, label: str) -> BettingResult:
        state = self.state
        start_idx = state.current_player_index
        betting = BettingRound(state, start_idx,
                               GamePhase[label] if label != "PREFLOP" else GamePhase.PREFLOP)

        current_pid = betting.next_to_act()
        if current_pid is None:
            return BettingResult.ROUND_COMPLETE

        while True:
            player = state.get_player(current_pid)
            if player is None:
                return BettingResult.ROUND_COMPLETE

            valid = betting.get_valid_actions(current_pid)

            if player.is_bot:
                action, amount = self._bot_decide(current_pid, valid)
                action_str = action.value
                if action == BettingAction.RAISE:
                    action_str = f"raises to {fmt_chips(amount)}"
                elif action == BettingAction.CALL:
                    action_str = f"calls {fmt_chips(valid.call_amount)}"
                elif action == BettingAction.ALL_IN:
                    action_str = f"{RED}ALL-IN{RESET}"
                else:
                    action_str = action.value
                print(f"  {DIM}{player.name}: {action_str}{RESET}")
            else:
                # Human turn
                print_table(state, self.human_id)
                action, amount = prompt_action(valid, state, player)

            result = betting.apply_action(current_pid, action, amount)

            # Track contributions for side pots
            if action in (BettingAction.CALL, BettingAction.RAISE, BettingAction.ALL_IN):
                contributed = player.total_bet - self.pot_manager.get_contribution(current_pid)
                if contributed > 0:
                    self.pot_manager.add_contribution(
                        current_pid, contributed, player.is_all_in
                    )

            if result != BettingResult.CONTINUE:
                return result

            current_pid = betting.next_to_act()
            if current_pid is None:
                return BettingResult.ROUND_COMPLETE

    def _bot_decide(self, player_id: str, valid: ValidActions) -> Tuple[BettingAction, int]:
        bot = BotPlayer(player_id)
        ps = self.state.get_player(player_id)
        if not ps:
            return BettingAction.FOLD, 0
        return bot.decide(self.state, ps, valid, self.difficulty)

    def _showdown(self) -> None:
        state = self.state
        active = state.active_players
        scores = {}
        for p in active:
            scores[p.player_id] = eval_best(p.hole_cards + state.community_cards)

        active_ids = [p.player_id for p in active]
        side_pots = self.pot_manager.calculate_side_pots(active_ids)

        if not side_pots:
            from app.core.pot import SidePot
            side_pots = [SidePot(amount=state.pot, eligible_player_ids=active_ids)]

        winners_info = []
        for pot in side_pots:
            eligible = [p for p in active if p.player_id in pot.eligible_player_ids]
            if not eligible:
                continue
            best = min(scores[p.player_id] for p in eligible)
            pot_winners = [p for p in eligible if scores[p.player_id] == best]
            share = pot.amount // len(pot_winners)
            remainder = pot.amount % len(pot_winners)
            for i, w in enumerate(pot_winners):
                award = share + (remainder if i == 0 else 0)
                w.chips += award
                winners_info.append({
                    "player_id": w.player_id,
                    "name": w.name,
                    "amount": award,
                    "hand": rank_to_string(best),
                })

        state.pot = 0
        print_hand_result(state, winners_info, scores, self.human_id)

    def _award_last(self) -> None:
        state = self.state
        active = state.active_players
        if len(active) == 1:
            w = active[0]
            w.chips += state.pot
            print(f"\n  {GREEN}{BOLD}{w.name} wins {fmt_chips(state.pot)}{RESET}"
                  f"  (everyone else folded)\n")
            state.pot = 0


# -- Entry point ---------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Texas Hold'em Poker — CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  python cli.py                            1 human + 3 medium bots
  python cli.py --bots 5 --difficulty hard  1 human + 5 hard bots
  python cli.py --variant fixed_limit       fixed-limit hold'em
  python cli.py --watch                     spectate bot-only game
  python cli.py --hands 5                   play 5 hands then stop
  python cli.py --blinds 50 100 --stack 10000
""",
    )
    parser.add_argument("--bots", type=int, default=3, help="number of bots (default: 3)")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard"], default="medium")
    parser.add_argument("--variant", choices=["no_limit", "fixed_limit"], default="no_limit")
    parser.add_argument("--blinds", nargs=2, type=int, metavar=("SB", "BB"), default=[10, 20])
    parser.add_argument("--stack", type=int, default=1000, help="starting stack (default: 1000)")
    parser.add_argument("--watch", action="store_true", help="spectate a bot-only game")
    parser.add_argument("--hands", type=int, default=0, help="number of hands to play (0=unlimited)")

    args = parser.parse_args()

    game = CLIGame(
        num_bots=args.bots,
        difficulty=args.difficulty,
        variant=args.variant,
        small_blind=args.blinds[0],
        big_blind=args.blinds[1],
        stack=args.stack,
        watch=args.watch,
        max_hands=args.hands,
    )
    game.run()


if __name__ == "__main__":
    main()
