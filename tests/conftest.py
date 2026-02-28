"""Shared fixtures for all tests."""
import asyncio
import pytest


@pytest.fixture(autouse=True)
def _ensure_event_loop():
    """Ensure a fresh event loop exists for every test.

    Python 3.9's asyncio.Event() requires a running loop at instantiation.
    After asyncio.run() finishes in one test, the loop is closed, which
    breaks subsequent tests that create PokerGame (it calls asyncio.Event()
    in __init__).  This fixture creates a new loop before each test and
    cleans it up afterward.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    loop.close()
