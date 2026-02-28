"""
Hand strength estimator using Monte Carlo simulation.

For preflop: precomputed Chen formula scores (fast) for easy/medium bots;
  1000 Monte Carlo sims for hard bots.
For postflop: 200–1000 Monte Carlo simulations.
"""
from __future__ import annotations
import random
from typing import List, Optional

from app.core.card import Card, Deck, Rank, Suit
from app.core.hand_evaluator import eval_best


# ---------------------------------------------------------------------------
# Chen formula for preflop hand strength (fast, approximate)
# ---------------------------------------------------------------------------

def chen_score(hole_cards: List[Card]) -> float:
    """
    Chen formula: approximate preflop hand strength as a score 0-20.
    Higher = stronger hand.
    """
    if len(hole_cards) != 2:
        return 0.0

    c1, c2 = sorted(hole_cards, key=lambda c: c.rank._value_, reverse=True)
    r1 = c1.rank._value_
    r2 = c2.rank._value_
    suited = c1.suit == c2.suit
    gap = r1 - r2

    # Base score from high card
    score_map = {14: 10, 13: 8, 12: 7, 11: 6}
    score = score_map.get(r1, r1 / 2.0)

    # Pair: double it (min 5)
    if r1 == r2:
        score = max(score * 2, 5)
        return score

    # Suited bonus
    if suited:
        score += 2

    # Gap penalty
    gap_penalties = {0: 0, 1: 0, 2: -1, 3: -2, 4: -4}
    score += gap_penalties.get(gap, -5)

    # Connected bonus (straight potential)
    if gap <= 1 and r1 <= 11:
        score += 1

    return max(score, 0)


def preflop_equity_fast(hole_cards: List[Card]) -> float:
    """Chen score normalized to [0, 1] range."""
    return min(chen_score(hole_cards) / 20.0, 1.0)


# ---------------------------------------------------------------------------
# Monte Carlo equity estimator
# ---------------------------------------------------------------------------

def _all_cards() -> List[Card]:
    """Return all 52 cards."""
    return [Card(rank, suit) for suit in Suit for rank in Rank]


def monte_carlo_equity(
    hole_cards: List[Card],
    community_cards: List[Card],
    num_opponents: int,
    simulations: int = 500,
) -> float:
    """
    Estimate win equity for our hand vs `num_opponents` random hands.

    Returns a float [0, 1] representing win probability (ties count as 0.5).
    """
    known_cards = set(str(c) for c in hole_cards + community_cards)
    deck = [c for c in _all_cards() if str(c) not in known_cards]

    wins = 0.0
    board_needed = 5 - len(community_cards)

    for _ in range(simulations):
        random.shuffle(deck)
        ptr = 0

        # Deal community cards
        board = list(community_cards)
        board.extend(deck[ptr:ptr + board_needed])
        ptr += board_needed

        # Deal opponent hole cards
        opp_hands: List[List[Card]] = []
        for _ in range(num_opponents):
            opp_hands.append([deck[ptr], deck[ptr + 1]])
            ptr += 2

        # Evaluate
        our_score = eval_best(hole_cards + board)
        our_best = our_score

        best_opp = min(eval_best(hand + board) for hand in opp_hands)

        if our_best < best_opp:
            wins += 1.0
        elif our_best == best_opp:
            wins += 0.5

    return wins / simulations


class HandStrengthEstimator:
    """
    Entry point for hand strength estimation.

    difficulty: "easy" | "medium" | "hard"
    """

    def estimate(
        self,
        hole_cards: List[Card],
        community_cards: List[Card],
        num_opponents: int,
        difficulty: str = "medium",
    ) -> float:
        """
        Return equity estimate [0, 1].
        """
        if not hole_cards:
            return 0.5

        num_opponents = max(1, num_opponents)

        if not community_cards:
            # Preflop
            if difficulty == "hard":
                sims = 1000
            elif difficulty == "medium":
                # Use Chen formula for speed
                return preflop_equity_fast(hole_cards)
            else:
                # Easy: rough Chen
                return preflop_equity_fast(hole_cards) * 0.9
            return monte_carlo_equity(hole_cards, [], num_opponents, sims)
        else:
            # Postflop
            if difficulty == "hard":
                sims = 1000
            elif difficulty == "medium":
                sims = 300
            else:
                sims = 100
            return monte_carlo_equity(hole_cards, community_cards, num_opponents, sims)
