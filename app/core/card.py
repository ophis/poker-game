"""Card, Rank, Suit, and Deck definitions."""
from __future__ import annotations
import random
from dataclasses import dataclass
from enum import Enum


# Primes assigned to each rank (used by Cactus Kev evaluator)
_RANK_PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41]


class Suit(Enum):
    def __new__(cls, symbol: str, bit: int):
        obj = object.__new__(cls)
        obj._value_ = symbol
        obj.bit = bit
        return obj

    CLUBS = ("c", 0x8000)
    DIAMONDS = ("d", 0x4000)
    HEARTS = ("h", 0x2000)
    SPADES = ("s", 0x1000)

    @property
    def symbol(self) -> str:
        return self._value_

    def __str__(self) -> str:
        return self._value_


class Rank(Enum):
    def __new__(cls, rank_value: int, symbol: str, prime: int):
        obj = object.__new__(cls)
        obj._value_ = rank_value
        obj.symbol = symbol
        obj.prime = prime
        return obj

    TWO   = (2,  "2", _RANK_PRIMES[0])
    THREE = (3,  "3", _RANK_PRIMES[1])
    FOUR  = (4,  "4", _RANK_PRIMES[2])
    FIVE  = (5,  "5", _RANK_PRIMES[3])
    SIX   = (6,  "6", _RANK_PRIMES[4])
    SEVEN = (7,  "7", _RANK_PRIMES[5])
    EIGHT = (8,  "8", _RANK_PRIMES[6])
    NINE  = (9,  "9", _RANK_PRIMES[7])
    TEN   = (10, "10", _RANK_PRIMES[8])
    JACK  = (11, "J", _RANK_PRIMES[9])
    QUEEN = (12, "Q", _RANK_PRIMES[10])
    KING  = (13, "K", _RANK_PRIMES[11])
    ACE   = (14, "A", _RANK_PRIMES[12])

    def __str__(self) -> str:
        return self.symbol

    def __lt__(self, other: "Rank") -> bool:
        return self._value_ < other._value_


@dataclass(frozen=True)
class Card:
    rank: Rank
    suit: Suit

    def to_int(self) -> int:
        """
        Encode card as Cactus Kev 32-bit integer:
        +--------+--------+--------+--------+
        |xxxbbbbb|bbbbbbbb|cdhsrrrr|xxpppppp|
        +--------+--------+--------+--------+
        b = rank bit (one-hot, bit 16+rank_index)
        cdhs = suit bits (bits 12-15)
        rrrr = rank nibble (bits 8-11)
        pppppp = prime number (bits 0-5)
        """
        rank_index = self.rank._value_ - 2  # 0–12
        rank_bit = 1 << (16 + rank_index)
        suit_bit = self.suit.bit
        rank_nibble = rank_index << 8
        prime = self.rank.prime
        return rank_bit | suit_bit | rank_nibble | prime

    def __str__(self) -> str:
        return f"{self.rank}{self.suit}"

    def __repr__(self) -> str:
        return f"Card({self})"


class Deck:
    def __init__(self) -> None:
        self._cards: list[Card] = []
        self.reset()

    def reset(self) -> None:
        self._cards = [Card(rank, suit) for suit in Suit for rank in Rank]
        random.shuffle(self._cards)

    def shuffle(self) -> None:
        random.shuffle(self._cards)

    def deal(self, n: int = 1) -> list[Card]:
        if n > len(self._cards):
            raise ValueError(f"Not enough cards: requested {n}, have {len(self._cards)}")
        dealt = self._cards[:n]
        self._cards = self._cards[n:]
        return dealt

    def deal_one(self) -> Card:
        return self.deal(1)[0]

    def __len__(self) -> int:
        return len(self._cards)
