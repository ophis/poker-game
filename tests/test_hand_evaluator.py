"""Unit tests for hand_evaluator.py"""
import pytest
from app.core.card import Card, Rank, Suit, Deck
from app.core.hand_evaluator import eval_5, eval_7, rank_to_class, rank_to_string, HandClass


def make_cards(*specs: str) -> list[Card]:
    """Parse cards like 'Ah', 'Kd', '10c', '2s'."""
    rank_map = {
        '2': Rank.TWO, '3': Rank.THREE, '4': Rank.FOUR, '5': Rank.FIVE,
        '6': Rank.SIX, '7': Rank.SEVEN, '8': Rank.EIGHT, '9': Rank.NINE,
        '10': Rank.TEN, 'J': Rank.JACK, 'Q': Rank.QUEEN, 'K': Rank.KING, 'A': Rank.ACE,
    }
    suit_map = {'c': Suit.CLUBS, 'd': Suit.DIAMONDS, 'h': Suit.HEARTS, 's': Suit.SPADES}
    return [Card(rank_map[s[:-1]], suit_map[s[-1]]) for s in specs]


class TestEval5:
    def test_royal_flush_score_1(self):
        cards = make_cards('Ah', 'Kh', 'Qh', 'Jh', '10h')
        assert eval_5(cards) == 1

    def test_worst_straight_flush(self):
        cards = make_cards('5h', '4h', '3h', '2h', 'Ah')
        score = eval_5(cards)
        assert score == 10  # Wheel straight flush

    def test_four_aces_best_quads(self):
        cards = make_cards('Ah', 'Ad', 'As', 'Ac', 'Kh')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.FOUR_OF_A_KIND
        assert score == 11

    def test_full_house(self):
        cards = make_cards('Ah', 'Ad', 'As', 'Kh', 'Kd')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.FULL_HOUSE
        assert score == 167

    def test_flush(self):
        cards = make_cards('Ah', 'Kh', 'Qh', 'Jh', '9h')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.FLUSH

    def test_straight_ace_high(self):
        cards = make_cards('Ah', 'Kd', 'Qc', 'Js', '10h')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.STRAIGHT
        assert score == 1600

    def test_straight_wheel(self):
        cards = make_cards('Ah', '2d', '3c', '4s', '5h')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.STRAIGHT
        assert score == 1609

    def test_three_of_a_kind(self):
        cards = make_cards('Ah', 'Ad', 'As', 'Kh', 'Qd')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.THREE_OF_A_KIND

    def test_two_pair(self):
        cards = make_cards('Ah', 'Ad', 'Kh', 'Kd', 'Qc')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.TWO_PAIR

    def test_one_pair(self):
        cards = make_cards('Ah', 'Ad', 'Kh', 'Qd', 'Jc')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.ONE_PAIR

    def test_high_card(self):
        cards = make_cards('Ah', 'Kd', 'Qc', 'Js', '9h')
        score = eval_5(cards)
        assert rank_to_class(score) == HandClass.HIGH_CARD

    def test_worst_hand(self):
        cards = make_cards('7h', '5d', '4c', '3s', '2h')
        score = eval_5(cards)
        assert score == 7462

    def test_better_flush_beats_worse(self):
        nut_flush = make_cards('Ah', 'Kh', 'Qh', 'Jh', '9h')
        low_flush = make_cards('9c', '8c', '7c', '6c', '4c')
        assert eval_5(nut_flush) < eval_5(low_flush)

    def test_better_straight_beats_worse(self):
        high = make_cards('Ah', 'Kd', 'Qc', 'Js', '10h')
        low = make_cards('6h', '5d', '4c', '3s', '2h')
        assert eval_5(high) < eval_5(low)


class TestEval7:
    def test_picks_best_5_from_7(self):
        # AA on board AAKKQ → four aces
        cards = make_cards('Ah', 'Ad', 'As', 'Ac', 'Kh', 'Kd', 'Qc')
        score = eval_7(cards)
        assert rank_to_class(score) == HandClass.FOUR_OF_A_KIND

    def test_uses_community_cards(self):
        # Hole: 2c 3h, Board: 4s 5d Ah Kh Qh
        # Best: A-high straight (A2345) or broadway straight with board
        cards = make_cards('2c', '3h', '4s', '5d', 'Ah', 'Kh', 'Qh')
        score = eval_7(cards)
        assert rank_to_class(score) == HandClass.STRAIGHT

    def test_7_high_card(self):
        cards = make_cards('7h', '5d', '4c', '3s', '2h', '6d', '8s')
        score = eval_7(cards)
        # Best 5: 8-7-6-5-4 — a straight!
        assert rank_to_class(score) == HandClass.STRAIGHT


class TestRankToString:
    def test_straight_flush(self):
        cards = make_cards('Ah', 'Kh', 'Qh', 'Jh', '10h')
        assert rank_to_string(eval_5(cards)) == "Straight Flush"

    def test_high_card(self):
        cards = make_cards('Ah', 'Kd', 'Qc', 'Js', '9h')
        assert rank_to_string(eval_5(cards)) == "High Card"


class TestEvalBest:
    def test_eval_best_5_cards(self):
        cards = make_cards('Ah', 'Kh', 'Qh', 'Jh', '10h')
        from app.core.hand_evaluator import eval_best
        assert eval_best(cards) == 1

    def test_eval_best_6_cards(self):
        from app.core.hand_evaluator import eval_best
        cards = make_cards('Ah', 'Kh', 'Qh', 'Jh', '10h', '2c')
        score = eval_best(cards)
        assert score == 1  # Royal flush from best 5

    def test_eval_best_7_cards(self):
        from app.core.hand_evaluator import eval_best
        cards = make_cards('Ah', 'Kh', 'Qh', 'Jh', '10h', '2c', '3d')
        score = eval_best(cards)
        assert score == 1

    def test_eval_best_invalid_count(self):
        from app.core.hand_evaluator import eval_best
        cards = make_cards('Ah', 'Kh', 'Qh', 'Jh')
        with pytest.raises(ValueError):
            eval_best(cards)


class TestCardEncoding:
    def test_all_52_cards_unique(self):
        deck = Deck()
        deck.reset()
        ints = [c.to_int() for c in deck._cards]
        assert len(set(ints)) == 52

    def test_card_string_representation(self):
        c = Card(Rank.ACE, Suit.HEARTS)
        assert str(c) == "Ah"
        c2 = Card(Rank.TEN, Suit.CLUBS)
        assert str(c2) == "10c"

    def test_card_repr(self):
        c = Card(Rank.ACE, Suit.HEARTS)
        assert repr(c) == "Card(Ah)"

    def test_suit_str(self):
        assert str(Suit.HEARTS) == "h"
        assert str(Suit.SPADES) == "s"

    def test_suit_symbol(self):
        assert Suit.HEARTS.symbol == "h"

    def test_rank_str(self):
        assert str(Rank.ACE) == "A"
        assert str(Rank.TEN) == "10"

    def test_rank_lt(self):
        assert Rank.TWO < Rank.ACE
        assert not (Rank.ACE < Rank.KING)

    def test_deck_shuffle(self):
        deck = Deck()
        cards_before = list(deck._cards)
        deck.shuffle()
        # Shuffled — same cards, possibly different order
        assert len(deck._cards) == 52

    def test_deck_deal(self):
        deck = Deck()
        cards = deck.deal(5)
        assert len(cards) == 5
        assert len(deck) == 47

    def test_deck_deal_one(self):
        deck = Deck()
        card = deck.deal_one()
        assert isinstance(card, Card)
        assert len(deck) == 51

    def test_deck_deal_too_many(self):
        deck = Deck()
        with pytest.raises(ValueError):
            deck.deal(53)
