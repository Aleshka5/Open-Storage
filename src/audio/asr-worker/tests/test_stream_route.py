"""WS route `/v1/stream`: the socket close code reaches the client (defect D4).

`StreamHandler.loop` computes 4408 (idle) / 4400 (overflow) / 1000 (normal), but
the route used to close the socket hard with `1000` — the client never got the reason. The
handler tests looked at `handler.close_code` directly and never checked the route, so the
defect slipped through review twice. Here is a guard on the route source.
"""

from __future__ import annotations

import ast
import pathlib

from app import main as app_main


def _stream_route_source() -> ast.AsyncFunctionDef:
    src = pathlib.Path(app_main.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "stream":
            return node
    raise AssertionError("the stream route was not found")


def test_route_closes_with_handler_code_not_literal_1000():
    """`websocket.close(code=...)` takes the code from the handler, not the literal 1000.

    D4 regression: `await websocket.close(code=1000)` at the end of `try` is exactly what
    hid 4408 (idle) and 4400 (frame overflow) from the client.
    """
    node = _stream_route_source()
    close_calls = [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "close"
        and any(kw.arg == "code" for kw in call.keywords)
    ]
    assert close_calls, "no websocket.close(code=...) calls in the route"

    for call in close_calls:
        code_kw = next(kw for kw in call.keywords if kw.arg == "code")
        if isinstance(code_kw.value, ast.Constant) and code_kw.value.value == 1000:
            raise AssertionError(
                "the route closes with the literal 1000 — the client never sees 4408/4400"
            )


def test_route_reads_handler_close_code():
    """The route actually reads the handler's `close_code`."""
    node = _stream_route_source()
    attrs = {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute) and n.attr == "close_code"
    }
    assert "close_code" in attrs, "the route does not read handler.close_code"
