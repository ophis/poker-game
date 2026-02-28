"""
Cactus Kev hand evaluator — pure Python, no external files.

Scores: 1 (Royal Flush) to 7462 (7-high). Lower = better.

Score ranges:
  1–10:     Straight Flush
  11–166:   Four of a Kind
  167–322:  Full House
  323–1599: Flush
  1600–1609: Straight
  1610–2467: Three of a Kind
  2468–3325: Two Pair
  3326–6185: One Pair
  6186–7462: High Card
"""
from __future__ import annotations
from enum import Enum
from itertools import combinations
from typing import List

from app.core.card import Card


class HandClass(Enum):
    STRAIGHT_FLUSH = 1
    FOUR_OF_A_KIND = 2
    FULL_HOUSE = 3
    FLUSH = 4
    STRAIGHT = 5
    THREE_OF_A_KIND = 6
    TWO_PAIR = 7
    ONE_PAIR = 8
    HIGH_CARD = 9


# ---------------------------------------------------------------------------
# Lookup table construction
# ---------------------------------------------------------------------------

def _build_tables() -> tuple[dict, dict, list, list]:
    """Build Cactus Kev lookup tables at import time."""

    # All 7462 unique 5-card hand ranks, mapped from hash key → score
    straights_and_highcards: dict[int, int] = {}
    flush_table: dict[int, int] = {}   # XOR of one-hot rank bits → score
    unique5_table: dict[int, int] = {} # prime product → score (non-flush unique5)
    pairs_table: dict[int, int] = {}   # prime product → score (hands with pairs)

    # -----------------------------------------------------------------------
    # Helper: generate all 5-card rank combos and assign scores
    # We enumerate hands from best to worst, assigning consecutive integers.
    # -----------------------------------------------------------------------

    ranks_ordered = list(range(2, 15))  # 2–14 (ACE=14)
    primes = {2:2, 3:3, 4:5, 5:7, 6:11, 7:13, 8:17, 9:19, 10:23, 11:29, 12:31, 13:37, 14:41}

    def rank_bits(rank_list: list[int]) -> int:
        """One-hot bit mask for a set of ranks (bit 0 = rank 2)."""
        bits = 0
        for r in rank_list:
            bits |= (1 << (r - 2))
        return bits

    def prime_product(rank_list: list[int]) -> int:
        product = 1
        for r in rank_list:
            product *= primes[r]
        return product

    score = 1

    # --- Straight Flushes (scores 1–10) ---
    # A-K-Q-J-T down to A-2-3-4-5
    sf_straights = [
        [14, 13, 12, 11, 10],
        [13, 12, 11, 10, 9],
        [12, 11, 10, 9, 8],
        [11, 10, 9, 8, 7],
        [10, 9, 8, 7, 6],
        [9, 8, 7, 6, 5],
        [8, 7, 6, 5, 4],
        [7, 6, 5, 4, 3],
        [6, 5, 4, 3, 2],
        [5, 4, 3, 2, 14],  # Wheel: A-2-3-4-5
    ]
    for hand in sf_straights:
        bits = rank_bits(hand)
        flush_table[bits] = score
        score += 1

    # --- Four of a Kind (scores 11–166) ---
    # Ordered: AAAA-K, AAAA-Q, ..., AAAA-2, KKKK-A, ...
    for quad_rank in range(14, 1, -1):
        for kicker in range(14, 1, -1):
            if kicker == quad_rank:
                continue
            pp = prime_product([quad_rank, quad_rank, quad_rank, quad_rank, kicker])
            pairs_table[pp] = score
            score += 1

    # --- Full House (scores 167–322) ---
    for trips_rank in range(14, 1, -1):
        for pair_rank in range(14, 1, -1):
            if pair_rank == trips_rank:
                continue
            pp = prime_product([trips_rank, trips_rank, trips_rank, pair_rank, pair_rank])
            pairs_table[pp] = score
            score += 1

    # --- Flushes (scores 323–1599) ---
    # All 5-card rank combos that are NOT straights, best to worst
    all_5_combos = list(combinations(range(14, 1, -1), 5))
    straight_sets = {frozenset(s) for s in sf_straights}
    flush_hands = [c for c in all_5_combos if frozenset(c) not in straight_sets]
    for hand in flush_hands:
        bits = rank_bits(list(hand))
        flush_table[bits] = score
        score += 1

    # --- Straights (scores 1600–1609) ---
    straight_hands = [
        [14, 13, 12, 11, 10],
        [13, 12, 11, 10, 9],
        [12, 11, 10, 9, 8],
        [11, 10, 9, 8, 7],
        [10, 9, 8, 7, 6],
        [9, 8, 7, 6, 5],
        [8, 7, 6, 5, 4],
        [7, 6, 5, 4, 3],
        [6, 5, 4, 3, 2],
        [5, 4, 3, 2, 14],  # Wheel
    ]
    for hand in straight_hands:
        pp = prime_product(hand)
        unique5_table[pp] = score
        score += 1

    # --- Three of a Kind (scores 1610–2467) ---
    for trips_rank in range(14, 1, -1):
        kickers = [r for r in range(14, 1, -1) if r != trips_rank]
        for k1, k2 in combinations(kickers, 2):
            pp = prime_product([trips_rank, trips_rank, trips_rank, k1, k2])
            pairs_table[pp] = score
            score += 1

    # --- Two Pair (scores 2468–3325) ---
    for p1 in range(14, 1, -1):
        for p2 in range(p1 - 1, 1, -1):
            kickers = [r for r in range(14, 1, -1) if r != p1 and r != p2]
            for k in kickers:
                pp = prime_product([p1, p1, p2, p2, k])
                pairs_table[pp] = score
                score += 1

    # --- One Pair (scores 3326–6185) ---
    for pair_rank in range(14, 1, -1):
        kickers = [r for r in range(14, 1, -1) if r != pair_rank]
        for k1, k2, k3 in combinations(kickers, 3):
            pp = prime_product([pair_rank, pair_rank, k1, k2, k3])
            pairs_table[pp] = score
            score += 1

    # --- High Card (scores 6186–7462) ---
    for hand in flush_hands:
        pp = prime_product(list(hand))
        unique5_table[pp] = score
        score += 1

    return flush_table, unique5_table, pairs_table, primes


_FLUSH_TABLE, _UNIQUE5_TABLE, _PAIRS_TABLE, _PRIMES = _build_tables()


# ---------------------------------------------------------------------------
# Evaluation functions
# ---------------------------------------------------------------------------

def _eval_5_ints(c1: int, c2: int, c3: int, c4: int, c5: int) -> int:
    """Evaluate 5 cards given as Cactus Kev integers."""
    # Check for flush: all 4 suit bits are the same
    suit_mask = 0xF000
    if (c1 & suit_mask) == (c2 & suit_mask) == (c3 & suit_mask) == (c4 & suit_mask) == (c5 & suit_mask):
        # Use rank bits (bits 16+) XOR'd together for lookup
        rank_bits = ((c1 | c2 | c3 | c4 | c5) >> 16) & 0x1FFF
        return _FLUSH_TABLE[rank_bits]

    # Prime product for non-flush lookup
    prime_product = (
        (c1 & 0x3F) * (c2 & 0x3F) * (c3 & 0x3F) * (c4 & 0x3F) * (c5 & 0x3F)
    )

    result = _UNIQUE5_TABLE.get(prime_product)
    if result is not None:
        return result

    return _PAIRS_TABLE[prime_product]


def eval_5(cards: List[Card]) -> int:
    """Evaluate a 5-card hand. Returns score 1–7462 (lower=better)."""
    assert len(cards) == 5, f"eval_5 requires exactly 5 cards, got {len(cards)}"
    ints = [c.to_int() for c in cards]
    return _eval_5_ints(*ints)


def eval_7(cards: List[Card]) -> int:
    """Evaluate best 5-card hand from 7 cards. Returns score 1–7462 (lower=better)."""
    assert len(cards) == 7, f"eval_7 requires exactly 7 cards, got {len(cards)}"
    best = 9999
    for combo in combinations(cards, 5):
        score = eval_5(list(combo))
        if score < best:
            best = score
    return best


def eval_best(cards: List[Card]) -> int:
    """Evaluate best 5-card hand from 5–7 cards."""
    n = len(cards)
    if n == 5:
        return eval_5(cards)
    elif n == 6:
        best = 9999
        for combo in combinations(cards, 5):
            score = eval_5(list(combo))
            if score < best:
                best = score
        return best
    elif n == 7:
        return eval_7(cards)
    else:
        raise ValueError(f"eval_best requires 5–7 cards, got {n}")


def rank_to_class(score: int) -> HandClass:
    if score <= 10:
        return HandClass.STRAIGHT_FLUSH
    elif score <= 166:
        return HandClass.FOUR_OF_A_KIND
    elif score <= 322:
        return HandClass.FULL_HOUSE
    elif score <= 1599:
        return HandClass.FLUSH
    elif score <= 1609:
        return HandClass.STRAIGHT
    elif score <= 2467:
        return HandClass.THREE_OF_A_KIND
    elif score <= 3325:
        return HandClass.TWO_PAIR
    elif score <= 6185:
        return HandClass.ONE_PAIR
    else:
        return HandClass.HIGH_CARD


_CLASS_NAMES = {
    HandClass.STRAIGHT_FLUSH: "Straight Flush",
    HandClass.FOUR_OF_A_KIND: "Four of a Kind",
    HandClass.FULL_HOUSE: "Full House",
    HandClass.FLUSH: "Flush",
    HandClass.STRAIGHT: "Straight",
    HandClass.THREE_OF_A_KIND: "Three of a Kind",
    HandClass.TWO_PAIR: "Two Pair",
    HandClass.ONE_PAIR: "One Pair",
    HandClass.HIGH_CARD: "High Card",
}


def rank_to_string(score: int) -> str:
    hc = rank_to_class(score)
    return _CLASS_NAMES[hc]
