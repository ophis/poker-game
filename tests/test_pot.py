"""Unit tests for pot.py"""
import pytest
from app.core.pot import PotManager, SidePot


class TestPotManagerBasic:
    def test_empty_pot(self):
        pm = PotManager()
        assert pm.total == 0
        assert pm.calculate_side_pots() == []

    def test_single_contribution(self):
        pm = PotManager()
        pm.add_contribution("p1", 100)
        assert pm.total == 100

    def test_multiple_contributions_same_player(self):
        pm = PotManager()
        pm.add_contribution("p1", 50)
        pm.add_contribution("p1", 50)
        assert pm.get_contribution("p1") == 100
        assert pm.total == 100

    def test_reset(self):
        pm = PotManager()
        pm.add_contribution("p1", 200)
        pm.reset()
        assert pm.total == 0
        assert pm.get_contribution("p1") == 0


class TestSidePots:
    def test_no_all_in_single_pot(self):
        pm = PotManager()
        pm.add_contribution("p1", 100)
        pm.add_contribution("p2", 100)
        pm.add_contribution("p3", 100)
        pots = pm.calculate_side_pots(["p1", "p2", "p3"])
        assert len(pots) == 1
        assert pots[0].amount == 300
        assert set(pots[0].eligible_player_ids) == {"p1", "p2", "p3"}

    def test_one_player_all_in(self):
        """
        P1 all-in for 50, P2 calls 100, P3 calls 100.
        Side pot 1: 50*3 = 150, eligible: p1, p2, p3
        Main pot: 50*2 = 100, eligible: p2, p3
        """
        pm = PotManager()
        pm.add_contribution("p1", 50, is_all_in=True)
        pm.add_contribution("p2", 100)
        pm.add_contribution("p3", 100)
        pots = pm.calculate_side_pots(["p1", "p2", "p3"])
        assert len(pots) == 2
        assert pots[0].amount == 150
        assert set(pots[0].eligible_player_ids) == {"p1", "p2", "p3"}
        assert pots[1].amount == 100
        assert set(pots[1].eligible_player_ids) == {"p2", "p3"}

    def test_two_players_all_in(self):
        """
        P1 all-in 30, P2 all-in 80, P3 calls 100.
        Pot 1: 30*3 = 90, eligible: p1, p2, p3
        Pot 2: (80-30)*2 = 100, eligible: p2, p3
        Main: (100-80)*1 = 20, eligible: p3
        Wait — p3 only, so actually p3 should be eligible for main pot.
        Actually the main pot goes to p2 and p3 (both active and above p1's cap).
        Let me re-check: p3 puts in 100 total, p2 put in 80 total, p1 put in 30 total.
        Pot 1 (cap 30): p1 contributes 30, p2 contributes 30, p3 contributes 30 → 90 chips, eligible: p1,p2,p3
        Pot 2 (cap 80): p2 contributes 50, p3 contributes 50 → 100 chips, eligible: p2,p3
        Main pot: p3 contributes 20 → 20 chips, eligible: p3 only
        """
        pm = PotManager()
        pm.add_contribution("p1", 30, is_all_in=True)
        pm.add_contribution("p2", 80, is_all_in=True)
        pm.add_contribution("p3", 100)
        pots = pm.calculate_side_pots(["p1", "p2", "p3"])
        assert len(pots) == 3
        assert pots[0].amount == 90
        assert set(pots[0].eligible_player_ids) == {"p1", "p2", "p3"}
        assert pots[1].amount == 100
        assert set(pots[1].eligible_player_ids) == {"p2", "p3"}
        assert pots[2].amount == 20
        assert set(pots[2].eligible_player_ids) == {"p3"}

    def test_folded_player_not_eligible(self):
        """
        P1 folds after contributing 50, P2 calls 100, P3 calls 100.
        All 250 chips go to pot, but p1 is not eligible.
        """
        pm = PotManager()
        pm.add_contribution("p1", 50)
        pm.add_contribution("p2", 100)
        pm.add_contribution("p3", 100)
        # p1 folded — only p2 and p3 are active
        pots = pm.calculate_side_pots(["p2", "p3"])
        # No all-ins, so single main pot
        assert len(pots) == 1
        assert pots[0].amount == 250
        assert set(pots[0].eligible_player_ids) == {"p2", "p3"}

    def test_total_chips_preserved(self):
        """Total chips in all side pots must equal total contributions."""
        pm = PotManager()
        pm.add_contribution("p1", 30, is_all_in=True)
        pm.add_contribution("p2", 80, is_all_in=True)
        pm.add_contribution("p3", 100)
        pots = pm.calculate_side_pots(["p1", "p2", "p3"])
        assert sum(p.amount for p in pots) == pm.total

    def test_none_active_uses_all_contributors(self):
        """When active_player_ids is None, all contributors are eligible."""
        pm = PotManager()
        pm.add_contribution("p1", 100)
        pm.add_contribution("p2", 100)
        pots = pm.calculate_side_pots(None)
        assert len(pots) == 1
        assert set(pots[0].eligible_player_ids) == {"p1", "p2"}

    def test_zero_contributions_returns_empty(self):
        """When all contributions are zero, return empty."""
        pm = PotManager()
        # No contributions at all
        pots = pm.calculate_side_pots(["p1"])
        assert pots == []


class TestPotManagerExtras:
    def test_negative_contribution_raises(self):
        pm = PotManager()
        with pytest.raises(ValueError):
            pm.add_contribution("p1", -10)

    def test_get_simple_total(self):
        pm = PotManager()
        pm.add_contribution("p1", 50)
        pm.add_contribution("p2", 100)
        assert pm.get_simple_total() == 150

    def test_contributions_snapshot(self):
        pm = PotManager()
        pm.add_contribution("p1", 50)
        pm.add_contribution("p2", 100)
        snap = pm.contributions_snapshot()
        assert snap == {"p1": 50, "p2": 100}
        # Snapshot is a copy
        snap["p1"] = 999
        assert pm.get_contribution("p1") == 50

    def test_side_pot_repr(self):
        sp = SidePot(amount=100, eligible_player_ids=["p1", "p2"])
        r = repr(sp)
        assert "100" in r
        assert "p1" in r
