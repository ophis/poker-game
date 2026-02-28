"""Pot and side pot management."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class SidePot:
    amount: int
    eligible_player_ids: List[str]

    def __repr__(self) -> str:
        return f"SidePot(amount={self.amount}, eligible={self.eligible_player_ids})"


class PotManager:
    """
    Tracks player contributions and computes side pots correctly.

    Usage:
        pm = PotManager()
        pm.add_contribution(player_id, amount)  # call per action
        pots = pm.calculate_side_pots()          # call after each betting round
    """

    def __init__(self) -> None:
        # contributions[player_id] = total chips contributed this hand
        self._contributions: Dict[str, int] = {}
        # all-in amounts keyed by player_id (only set players who are all-in)
        self._all_in_amounts: Dict[str, int] = {}
        self._total: int = 0

    def reset(self) -> None:
        self._contributions.clear()
        self._all_in_amounts.clear()
        self._total = 0

    @property
    def total(self) -> int:
        return self._total

    def add_contribution(self, player_id: str, amount: int, is_all_in: bool = False) -> None:
        """Add chips from a player to the pot."""
        if amount < 0:
            raise ValueError(f"Contribution cannot be negative: {amount}")
        self._contributions[player_id] = self._contributions.get(player_id, 0) + amount
        self._total += amount
        if is_all_in:
            self._all_in_amounts[player_id] = self._contributions[player_id]

    def get_contribution(self, player_id: str) -> int:
        return self._contributions.get(player_id, 0)

    def calculate_side_pots(self, active_player_ids: Optional[List[str]] = None) -> List[SidePot]:
        """
        Calculate side pots from current contributions.

        active_player_ids: players still in the hand (not folded). If None,
            all contributors are considered active.

        Returns a list of SidePot objects ordered from smallest cap upward.
        The last pot is the main pot with no cap.
        """
        if not self._contributions:
            return []

        if active_player_ids is None:
            active_player_ids = list(self._contributions.keys())

        # Only consider players who contributed something
        contributors = {pid: amt for pid, amt in self._contributions.items() if amt > 0}
        if not contributors:
            return []

        # Find all unique contribution levels (caps) created by all-in players
        all_in_caps = sorted(set(self._all_in_amounts.values()))

        side_pots: List[SidePot] = []
        already_taken: Dict[str, int] = {pid: 0 for pid in contributors}
        remaining_caps = all_in_caps.copy()

        for cap in remaining_caps:
            pot_amount = 0
            eligible: List[str] = []
            for pid, total_contrib in contributors.items():
                contribution_to_this_pot = min(total_contrib, cap) - already_taken[pid]
                if contribution_to_this_pot > 0:
                    pot_amount += contribution_to_this_pot
                    already_taken[pid] += contribution_to_this_pot
                    # Eligible if active and contributed to this level
                    if pid in active_player_ids:
                        eligible.append(pid)
            if pot_amount > 0:
                side_pots.append(SidePot(amount=pot_amount, eligible_player_ids=eligible))

        # Main pot: everything above all caps
        main_pot_amount = 0
        main_eligible: List[str] = []
        for pid, total_contrib in contributors.items():
            leftover = total_contrib - already_taken[pid]
            if leftover > 0:
                main_pot_amount += leftover
                if pid in active_player_ids:
                    main_eligible.append(pid)

        if main_pot_amount > 0:
            side_pots.append(SidePot(amount=main_pot_amount, eligible_player_ids=main_eligible))

        return side_pots

    def get_simple_total(self) -> int:
        """Return total pot (use when no all-ins, for display)."""
        return self._total

    def contributions_snapshot(self) -> Dict[str, int]:
        return dict(self._contributions)
