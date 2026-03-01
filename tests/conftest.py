"""Shared fixtures for all tests."""
import asyncio
import socket
import subprocess
import sys
import time

import pytest


@pytest.fixture(autouse=True)
def _ensure_event_loop(request):
    """Ensure a fresh event loop exists for every *sync* test.

    Python 3.9's asyncio.Event() requires a running loop at instantiation.
    After asyncio.run() finishes in one test, the loop is closed, which
    breaks subsequent tests that create PokerGame (it calls asyncio.Event()
    in __init__).  This fixture creates a new loop before each test and
    cleans it up afterward.

    Async tests are skipped — pytest-asyncio manages their own event loops
    and this fixture must not interfere with that.
    """
    import inspect
    if inspect.iscoroutinefunction(request.node.obj):
        # Let pytest-asyncio handle the event loop for async tests
        yield
        return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    loop.close()


# ---------------------------------------------------------------------------
# Shared live-server fixture (used by both e2e and ws_integration tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_server():
    """Start a real uvicorn process on port 18000; yield; stop it.

    Port 18000 avoids clashing with a dev server on 8000.
    Session-scoped so the server starts once for the entire test session.
    """
    port = 18000
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--log-level", "warning",
        ],
    )
    # Poll until port is accepting connections (up to 6 s)
    deadline = time.time() + 6
    while time.time() < deadline:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            s.close()
            break
        except OSError:
            time.sleep(0.2)
    else:
        proc.terminate()
        raise RuntimeError("uvicorn did not start in time on port 18000")

    yield proc

    proc.terminate()
    proc.wait()
