"""A header with a non-ASCII value or name is not forwarded.

A browser in a non-English locale sends `date` in its own alphabet. rag-edge reads
raw header bytes as Latin-1, and httpx encodes a forwarded header as ASCII, so a
non-ASCII value used to raise in build_request and answer 500.
"""

from rag_edge.proxy import outgoing_request_headers

REQUEST_ID = "2b0c8f8e-1111-4222-8333-444455556666"

# utf-8 for "ср, 25 нояб. 2026 г.", as it arrives after the Latin-1 decode
CYRILLIC_DATE = b"\xd1\xf1, 25 \xed\xee\xff\xe1. 2026 \xe3.".decode("latin-1")


def _pairs(headers):
    return {name.lower(): value for name, value in headers}


def test_ascii_headers_are_forwarded():
    headers = [("x-auth-subject", "u"), ("accept", "text/html"), ("connection", "keep-alive")]
    out = _pairs(outgoing_request_headers(headers, REQUEST_ID))
    assert out["x-auth-subject"] == "u"
    assert out["accept"] == "text/html"
    assert out["x-request-id"] == REQUEST_ID


def test_client_date_is_dropped():
    out = _pairs(outgoing_request_headers([("date", CYRILLIC_DATE), ("accept", "*/*")], REQUEST_ID))
    assert "date" not in out
    assert out["accept"] == "*/*"


def test_non_ascii_value_in_any_header_is_dropped():
    out = _pairs(outgoing_request_headers([("x-user-agent", "Проверка"), ("accept", "*/*")], REQUEST_ID))
    assert "x-user-agent" not in out
    assert out["accept"] == "*/*"


def test_every_forwarded_header_is_ascii():
    headers = [("date", CYRILLIC_DATE), ("accept", "*/*"), ("x-auth-roles", "svc:rag:family")]
    for name, value in outgoing_request_headers(headers, REQUEST_ID):
        assert name.isascii() and value.isascii()
