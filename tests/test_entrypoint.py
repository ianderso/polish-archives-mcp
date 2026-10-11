"""The stdio entry point.

Nothing else in the suite calls ``run()``. In a sibling server a broken one
shipped: ``MCPServer.run`` is synchronous and drives its own event loop, so
wrapping it in ``asyncio.run()`` passed None where a coroutine was expected
and raised ValueError as the server stopped.
"""

from __future__ import annotations

import inspect
import os
import subprocess
import sys

from polish_archives_mcp import server


def test_the_server_run_method_is_synchronous():
    """The assumption the entry point rests on.

    If a future MCP release makes this a coroutine, ``run()`` has to change
    with it, and this test is what says so.
    """
    assert not inspect.iscoroutinefunction(server.mcp.run)


def test_the_entry_point_calls_run_without_wrapping_it(monkeypatch):
    """Calling it must not raise, and must actually start the server."""
    called: list[tuple] = []
    monkeypatch.setattr(server.mcp, "run", lambda *a, **k: called.append((a, k)))
    monkeypatch.setattr(server.logging, "basicConfig", lambda **k: None)

    server.run()

    assert called, "run() did not start the server"


def test_the_entry_point_does_not_wrap_run_in_asyncio():
    """A guard against the specific mistake, not just its symptom.

    Parsed rather than grepped: the source explains the mistake in a
    comment, and a substring search would match that.
    """
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(server.run)))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
    ]
    assert calls == []


def test_the_server_starts_and_exits_cleanly_on_end_of_input(tmp_path):
    """The real process: stdio with nothing on it must end, not hang or crash."""
    env = {**os.environ, "POLISH_ARCHIVES_CACHE_DIR": str(tmp_path / "cache")}
    done = subprocess.run(
        [sys.executable, "-m", "polish_archives_mcp"],
        input=b"",
        capture_output=True,
        timeout=30,
        env=env,
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr.decode()[-2000:]
