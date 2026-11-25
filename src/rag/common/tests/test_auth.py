from rag_common.auth import AuthError, AuthOk, authenticate

USER = "91a0b1c2-3d4e-4f50-8617-18293a4b5c6d"
OTHER = "6f1c0c3e-3c8a-4f0e-9a4a-1d2b3c4d5e6f"


def test_requires_subject_header() -> None:
    result = authenticate({})
    assert isinstance(result, AuthError)
    assert result.status == 401
    assert result.body["error"]["code"] == "unauthenticated"
    assert "details" not in result.body["error"]


def test_removed_identity_headers_are_ignored() -> None:
    # A request that carries only a pre-v1 header name has no subject.
    for name in ("X-Auth-User-Id", "X-User-Id", "X-Storage-Role"):
        result = authenticate({name: USER})
        assert isinstance(result, AuthError), name
        assert result.status == 401, name

    result = authenticate({"X-Auth-User-Id": OTHER, "X-Auth-Subject": USER})
    assert isinstance(result, AuthOk)
    assert result.user_id == USER


def test_authorization_and_cookie_do_not_authenticate() -> None:
    result = authenticate({"Authorization": "Bearer token", "Cookie": "auth_access=abc"})
    assert isinstance(result, AuthError)
    assert result.status == 401


def test_non_uuid_subject_is_401() -> None:
    for value in ("", "not-a-uuid", "91a0b1c23d4e4f50861718293a4b5c6d", "user"):
        result = authenticate({"X-Auth-Subject": value})
        assert isinstance(result, AuthError)
        assert result.status == 401


def test_canonical_lowercase() -> None:
    result = authenticate({"x-auth-subject": USER.upper()})
    assert isinstance(result, AuthOk)
    assert result.user_id == USER


def test_blocked_role_is_403_even_with_uuid() -> None:
    result = authenticate({"X-Auth-Subject": USER, "X-Auth-Roles": "svc:rag:blocked"})
    assert isinstance(result, AuthError)
    assert result.status == 403
    assert result.body["error"]["code"] == "forbidden"
    assert result.body["error"]["message"] == "User is blocked"


def test_blocked_without_subject_stays_401() -> None:
    result = authenticate({"X-Auth-Roles": "svc:rag:blocked"})
    assert isinstance(result, AuthError)
    assert result.status == 401


def test_other_roles_pass() -> None:
    for roles in (
        "svc:rag:family",
        "svc:rag:admin",
        "svc:rag:family svc:rag:admin",
        "default-roles-realm svc:rag:family",
    ):
        result = authenticate({"X-Auth-Subject": USER, "X-Auth-Roles": roles})
        assert isinstance(result, AuthOk), roles
        assert result.user_id == USER

    result = authenticate(
        {
            "X-Auth-Subject": USER,
            "X-Auth-Roles": "svc:rag:family",
            "X-Auth-Email": "a@example.com",
            "X-Auth-Name": "Ada",
        }
    )
    assert isinstance(result, AuthOk)


def test_roles_are_matched_as_whole_tokens_not_substrings() -> None:
    # A longer token that merely contains the blocked name must not deny.
    result = authenticate(
        {"X-Auth-Subject": USER, "X-Auth-Roles": "svc:rag:blocked:extra not-svc:rag:blocked"}
    )
    assert isinstance(result, AuthOk)


def test_blocked_among_several_roles_is_403() -> None:
    result = authenticate(
        {"X-Auth-Subject": USER, "X-Auth-Roles": "svc:rag:family svc:rag:blocked"}
    )
    assert isinstance(result, AuthError)
    assert result.status == 403


def test_blocked_role_list_is_whitespace_trimmed() -> None:
    result = authenticate({"X-Auth-Subject": USER, "X-Auth-Roles": "  svc:rag:blocked  "})
    assert isinstance(result, AuthError)
    assert result.status == 403
