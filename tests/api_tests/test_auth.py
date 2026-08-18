"""Authentication: proving who a token says you are, and refusing bad credentials."""

import allure
import pytest

# Every test here reads: logging in, reading identity back, and being
# refused. Nothing is created, so the whole module is safe to point at the
# deployed demo.
pytestmark = [pytest.mark.api, pytest.mark.readonly]


@pytest.mark.smoke
@allure.feature("Authentication")
@allure.story("A successful login identifies the caller's tenant and role")
def test_login_returns_a_token_that_identifies_the_user(api, settings):
    """The token is only useful if the identity behind it is right.

    Asserting that /auth/me echoes the tenant and role is the assertion that
    matters: the application decides every authorisation question from those
    two claims, so if they were wrong here, every RBAC and isolation test below
    would be testing the wrong user.
    """
    email = settings.user_email("admin", "acme")

    with allure.step(f"Log in as {email}"):
        token = api.auth().login(email, settings.seed_password)

    assert token.access_token, "login returned an empty token"
    assert token.token_type == "bearer"

    with allure.step("Ask the API who the token belongs to"):
        user = api.auth(role="admin", tenant="acme").me()

    assert user.email == email
    assert user.tenant_id == "acme"
    assert user.role == "admin"


@allure.feature("Authentication")
@allure.story("A wrong password is refused")
def test_login_with_a_wrong_password_is_rejected(api, settings):
    """401, and no token in the body.

    The second assertion is the one worth having. A endpoint that returns 401
    while still including a usable token in the body would pass a status-only
    check and be a complete authentication bypass.
    """
    response = api.auth().login_response(
        settings.user_email("admin", "acme"), "definitely-not-the-password"
    )

    assert response.status_code == 401
    assert "access_token" not in response.text


@allure.feature("Authentication")
@allure.story("The OAuth2 form endpoint issues a usable token")
def test_the_oauth2_form_endpoint_also_issues_a_token(api, settings):
    """The same credentials through the other door.

    The application exposes both a JSON login and the OAuth2 password flow that
    the /docs Authorize button uses. They must agree — if the form endpoint
    drifted, every manual exploration through /docs would be authenticating as
    something the automated tests never exercise.
    """
    email = settings.user_email("admin", "acme")

    response = api.auth().login_form_response(email, settings.seed_password)

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"], "the form endpoint returned an empty token"


@allure.feature("Authentication")
@allure.story("An unauthenticated request is refused")
def test_a_request_with_no_token_is_refused(api):
    response = api.auth().me_response()

    assert response.status_code == 401, (
        "an anonymous caller could read /auth/me"
    )


@allure.feature("Authentication")
@allure.story("A forged token is refused")
def test_a_forged_token_is_refused(api, settings):
    """A token the server did not sign must not be accepted.

    The payload here is deliberately well-formed nonsense: the shape of a JWT
    without a valid signature. Accepting it would mean the signature is not
    being verified, which no status-code check on a *valid* token would ever
    reveal.
    """
    forged = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwicm9sZSI6ImFkbWluIn0.not-a-signature"

    response = api.auth().get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert response.status_code == 401, (
        f"a token with an invalid signature was accepted ({response.status_code}) "
        f"— signatures are not being verified"
    )
