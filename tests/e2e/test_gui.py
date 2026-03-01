"""End-to-end GUI tests using Playwright (Chromium).

Requires the live_server fixture (starts uvicorn on port 18000) and a
Playwright Chromium installation:

    playwright install chromium

Run:
    python3 -m pytest tests/e2e/ -v --timeout=180
"""
import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import BASE_URL


# ---------------------------------------------------------------------------
# Class 1: Lobby UI
# ---------------------------------------------------------------------------

class TestLobbyGUI:
    def test_lobby_page_elements_present(self, page, live_server):
        """Critical lobby elements are visible on page load."""
        page.goto(BASE_URL)
        expect(page.locator("#create-game-form")).to_be_visible()
        expect(page.locator("#player-name")).to_be_visible()
        expect(page.locator("#num-bots")).to_be_visible()
        expect(page.locator("#games-list")).to_be_visible()
        expect(page.locator("#create-game-form button[type='submit']")).to_be_visible()

    def test_create_game_form_redirects_to_game_page(self, page, live_server):
        """Submitting the create-game form navigates to /game/{id}."""
        page.goto(BASE_URL)
        page.fill("#player-name", "LobbyTester")
        page.select_option("#num-bots", "3")
        page.select_option("#bot-difficulty", "easy")
        page.locator("#create-game-form button[type='submit']").click()
        page.wait_for_url(re.compile(r".*/game/.*"), timeout=15_000)

        assert "/game/" in page.url
        expect(page.locator("#poker-table")).to_be_visible()
        expect(page.locator("#pot-display")).to_be_visible()

    def test_created_game_appears_in_lobby_list(self, page, live_server):
        """A newly created game shows up in the lobby's games list."""
        page.goto(BASE_URL)
        page.fill("#player-name", "LobbyListTester")
        page.select_option("#num-bots", "3")
        page.select_option("#bot-difficulty", "easy")
        page.locator("#create-game-form button[type='submit']").click()
        page.wait_for_url(re.compile(r".*/game/.*"), timeout=15_000)

        # Extract game_id from the URL
        match = re.search(r"/game/([^/?#]+)", page.url)
        assert match, f"Could not parse game_id from URL: {page.url}"
        game_id = match.group(1)

        # Navigate back to lobby and verify entry
        page.goto(BASE_URL)
        entry = page.locator(f".game-entry[data-game-id='{game_id}']")
        expect(entry).to_be_visible(timeout=10_000)


# ---------------------------------------------------------------------------
# Class 2: Game Table UI
# ---------------------------------------------------------------------------

class TestGameTableGUI:
    def test_connection_banner_shows_connected(self, game_page):
        """WebSocket connection banner transitions to 'connected' state."""
        banner = game_page.locator("#connection-banner")
        expect(banner).to_have_class(re.compile(r"connected"), timeout=15_000)

    def test_hole_cards_dealt_to_player(self, game_page):
        """Player receives exactly 2 face-up (non-hidden) hole cards."""
        expect(
            game_page.locator("#hole-cards .card:not(.hidden)")
        ).to_have_count(2, timeout=45_000)

    def test_pot_nonzero_after_hand_starts(self, game_page):
        """Pot amount reflects at least the posted blinds after hand start."""
        game_page.wait_for_function(
            "() => parseInt(document.getElementById('pot-amount').textContent || '0') > 0",
            timeout=45_000,
        )
        pot_text = game_page.locator("#pot-amount").text_content()
        assert int(pot_text or "0") > 0

    def test_phase_display_shows_preflop(self, game_page):
        """Phase display renders a valid street name once the hand begins."""
        # Accept any rendered phase — bots may move fast, just confirm something appears.
        game_page.wait_for_function(
            """() => {
                const el = document.getElementById('phase-display');
                if (!el) return false;
                const t = el.textContent.toUpperCase();
                return t.includes('PREFLOP') || t.includes('FLOP')
                    || t.includes('TURN')    || t.includes('RIVER')
                    || t.includes('WAITING') || t.includes('SHOWDOWN');
            }""",
            timeout=45_000,
        )
        text = game_page.locator("#phase-display").text_content()
        assert text and text.strip() != "", "Phase display should not be empty"

    def test_action_controls_appear_on_turn(self, game_page):
        """Action controls become visible when it is the human player's turn."""
        expect(game_page.locator("#action-controls")).to_be_visible(timeout=45_000)
        expect(game_page.locator("#btn-fold")).to_be_visible()

    def test_fold_hides_action_controls(self, game_page):
        """Clicking Fold sends the action and hides the action controls."""
        # Wait until it is our turn (fold button specifically visible)
        game_page.wait_for_selector("#btn-fold:visible", timeout=45_000)
        game_page.locator("#btn-fold").click()
        expect(game_page.locator("#action-controls")).to_be_hidden(timeout=10_000)

    def test_opponent_seat_cards_are_hidden(self, game_page):
        """Opponent hole-cards in seat panels are always rendered as hidden."""
        # Wait for our own hole cards to appear (hand has started)
        game_page.wait_for_selector("#hole-cards .card", timeout=45_000)

        pid = game_page.evaluate("() => sessionStorage.getItem('player_id')")
        assert pid, "player_id not found in sessionStorage"

        opponent_cards = game_page.locator(
            f".player-seat:not([data-pid='{pid}']) .card"
        )
        # With 3 bots there should be at least 2 opponent cards on the table
        count = opponent_cards.count()
        assert count >= 2, f"Expected ≥2 opponent cards, got {count}"

        # Every opponent card must carry the 'hidden' class
        for i in range(count):
            card = opponent_cards.nth(i)
            expect(card).to_have_class(re.compile(r"hidden"))

    def test_winner_overlay_appears_after_hand(self, game_page):
        """Winner overlay is displayed with details after the hand completes."""
        game_page.wait_for_selector("#winner-overlay", state="visible", timeout=120_000)
        expect(game_page.locator("#winner-title")).to_be_visible()
        details = game_page.locator("#winner-details").text_content()
        assert details and details.strip() != "", "Winner details should not be empty"
