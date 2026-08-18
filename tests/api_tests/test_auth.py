"""Authentication: proving who a token says you are, and refusing bad credentials."""

import allure
import pytest

pytestmark = [pytest.mark.api, pytest.mark.smoke]


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
