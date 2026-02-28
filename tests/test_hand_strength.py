"""Unit tests for hand_strength.py — Chen formula and Monte Carlo equity."""
import random
import pytest
from app.core.card import Card, Rank, Suit
from app.ai.hand_strength import (
    chen_score,
    preflop_equity_fast,
    monte_carlo_equity,
    HandStrengthEstimator,
)


def _card(rank: Rank, suit: Suit) -> Card:
    return Card(rank, suit)


class TestChenScore:
    def test_pair_aces(self):
        cards = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        score = chen_score(cards)
        # ACE base=10, pair doubles → 20
        assert score == 20

    def test_pair_twos(self):
        cards = [_card(Rank.TWO, Suit.SPADES), _card(Rank.TWO, Suit.HEARTS)]
        score = chen_score(cards)
        # TWO base=1.0, pair doubles → 2.0, but min 5
        assert score == 5

    def test_seven_two_offsuit(self):
        cards = [_card(Rank.SEVEN, Suit.SPADES), _card(Rank.TWO, Suit.HEARTS)]
        score = chen_score(cards)
        # 7 base=3.5, gap=5 → penalty -5, no suited bonus → max(3.5-5, 0)=0
        assert score == 0

    def test_suited_bonus(self):
        # AKs: base=10, suited +2, gap=1 → no penalty = 12
        suited = [_card(Rank.ACE, Suit.SPADES), _card(Rank.KING, Suit.SPADES)]
        offsuit = [_card(Rank.ACE, Suit.SPADES), _card(Rank.KING, Suit.HEARTS)]
        assert chen_score(suited) == chen_score(offsuit) + 2

    def test_gap_penalty(self):
        # A-Q: gap=2, penalty=-1
        cards = [_card(Rank.ACE, Suit.SPADES), _card(Rank.QUEEN, Suit.HEARTS)]
        score = chen_score(cards)
        # base=10, gap=2 → -1 = 9
        assert score == 9

    def test_straight_potential_bonus(self):
        # 10-9o: high card base = 10/2=5, gap=1, penalty=0
        # connected bonus: gap<=1 and r1<=11 → +1
        cards = [_card(Rank.TEN, Suit.SPADES), _card(Rank.NINE, Suit.HEARTS)]
        score = chen_score(cards)
        # base=5, gap=1 penalty=0, connected +1 = 6
        assert score == 6

    def test_no_connected_bonus_for_high_cards(self):
        # Q-J: gap=1, but r1=12 > 11 → no connected bonus
        cards = [_card(Rank.QUEEN, Suit.SPADES), _card(Rank.JACK, Suit.HEARTS)]
        score_qj = chen_score(cards)
        # base Q=7, gap=1 penalty=0, no connected bonus = 7
        assert score_qj == 7

    def test_empty_cards(self):
        assert chen_score([]) == 0.0

    def test_single_card(self):
        assert chen_score([_card(Rank.ACE, Suit.SPADES)]) == 0.0


class TestPreflopEquityFast:
    def test_normalization(self):
        cards = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        eq = preflop_equity_fast(cards)
        # chen=20, 20/20=1.0
        assert eq == 1.0

    def test_weak_hand_low_equity(self):
        cards = [_card(Rank.SEVEN, Suit.SPADES), _card(Rank.TWO, Suit.HEARTS)]
        eq = preflop_equity_fast(cards)
        assert eq == 0.0

    def test_clamping(self):
        # No hand should exceed 1.0
        cards = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        eq = preflop_equity_fast(cards)
        assert eq <= 1.0


class TestMonteCarloEquity:
    def test_aces_high_equity(self):
        random.seed(42)
        hole = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        eq = monte_carlo_equity(hole, [], num_opponents=1, simulations=500)
        # AA vs 1 random hand should be ~85%
        assert eq > 0.7

    def test_weak_hand_low_equity(self):
        random.seed(42)
        hole = [_card(Rank.SEVEN, Suit.SPADES), _card(Rank.TWO, Suit.HEARTS)]
        eq = monte_carlo_equity(hole, [], num_opponents=1, simulations=500)
        # 72o vs 1 random hand should be ~35%
        assert eq < 0.5

    def test_returns_between_0_and_1(self):
        random.seed(42)
        hole = [_card(Rank.KING, Suit.SPADES), _card(Rank.QUEEN, Suit.HEARTS)]
        eq = monte_carlo_equity(hole, [], num_opponents=1, simulations=100)
        assert 0.0 <= eq <= 1.0

    def test_with_community_cards(self):
        random.seed(42)
        hole = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        community = [
            _card(Rank.ACE, Suit.CLUBS),
            _card(Rank.KING, Suit.DIAMONDS),
            _card(Rank.TWO, Suit.CLUBS),
        ]
        eq = monte_carlo_equity(hole, community, num_opponents=1, simulations=200)
        # Trips aces on flop should have very high equity
        assert eq > 0.9


class TestHandStrengthEstimator:
    def test_empty_hole_cards(self):
        est = HandStrengthEstimator()
        eq = est.estimate([], [], num_opponents=1)
        assert eq == 0.5

    def test_easy_preflop_uses_chen(self):
        est = HandStrengthEstimator()
        hole = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        eq = est.estimate(hole, [], num_opponents=1, difficulty="easy")
        # easy = chen * 0.9 = 1.0 * 0.9 = 0.9
        assert abs(eq - 0.9) < 0.01

    def test_medium_preflop_uses_chen(self):
        est = HandStrengthEstimator()
        hole = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        eq = est.estimate(hole, [], num_opponents=1, difficulty="medium")
        assert eq == 1.0

    def test_hard_preflop_uses_monte_carlo(self):
        random.seed(42)
        est = HandStrengthEstimator()
        hole = [_card(Rank.ACE, Suit.SPADES), _card(Rank.ACE, Suit.HEARTS)]
        eq = est.estimate(hole, [], num_opponents=1, difficulty="hard")
        # MC with AA should be high
        assert eq > 0.7

    def test_postflop_uses_monte_carlo(self):
        random.seed(42)
        est = HandStrengthEstimator()
        hole = [_card(Rank.ACE, Suit.SPADES), _card(Rank.KING, Suit.SPADES)]
        community = [
            _card(Rank.QUEEN, Suit.SPADES),
            _card(Rank.JACK, Suit.SPADES),
            _card(Rank.TEN, Suit.SPADES),
        ]
        eq = est.estimate(hole, community, num_opponents=1, difficulty="medium")
        # Royal flush draw/made — very high equity
        assert eq > 0.9
