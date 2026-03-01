import re

import pytest

BASE_URL = "http://127.0.0.1:18000"


@pytest.fixture
def game_page(page, live_server):
    """Navigate to a freshly-created game table as a human player.

    Fills the lobby form with 3 easy bots (so hands complete quickly),
    submits, and waits for the game page URL. Returns the Page object
    already on /game/{game_id}.
    """
    page.goto(BASE_URL)
    page.fill("#player-name", "GUITester")
    page.select_option("#num-bots", "3")
    page.select_option("#bot-difficulty", "easy")
    page.locator("#create-game-form button[type='submit']").click()
    page.wait_for_url(re.compile(r".*/game/.*"), timeout=15_000)
    return page
