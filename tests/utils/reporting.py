"""How a test describes itself in the Allure report.

The report is read by people who did not write these tests, which makes its
structure part of the deliverable rather than a by-product. Default output
groups by file path, gives every test the same severity, and shows function
names — none of which mean anything to a reader who does not already know the
suite.

Everything here is derived centrally from the module a test lives in, so 138
tests gain structure without 138 decorators. Where the derivation would be
wrong, an explicit override says so by name — those are the only exceptions, and
they are listed rather than scattered.

Three labels do the work:

  epic      the product area — what part of Engage this is about
  feature   the finer grouping, usually the module's own @allure.feature
  story     the specific behaviour

The Behaviors tab renders exactly that tree, which is why the epic is a product
area and not a test layer: a reader asks "what does the app do about campaigns",
never "what is in api_tests".
"""

from __future__ import annotations

import re

# --- product areas ---------------------------------------------------------
#
# Keyed by module name. Tenant isolation sits under Auth deliberately: it is a
# question about who may see what, which is the same question authentication
# and RBAC answer, and a reader looking for "can one customer see another's
# data" looks under access control rather than under a module list.

MODULE_AREAS: dict[str, str] = {
    # API — access control
    "test_auth": "Auth",
    "test_rbac": "Auth",
    "test_tenant_isolation": "Auth",
    # API — domain
    "test_contacts_crud": "Contacts",
    "test_contacts_pagination": "Contacts",
    "test_segments_rules": "Segments",
    "test_campaign_states": "Campaigns",
    "test_delivery_idempotency": "Delivery",
    "test_analytics_invariants": "Analytics",
    # Platform-wide
    "test_reset_guard": "Platform",
    "test_storage_facts": "Platform",
    "test_seed_data": "Platform",
    "test_contract_openapi": "Platform",
    # Browser
    "test_login": "Auth",
    "test_rbac_ui": "Auth",
    "test_contacts_grid": "Contacts",
    "test_error_states": "Contacts",
    "test_analytics_data": "Analytics",
    # Journeys
    "test_campaign_lifecycle": "Campaigns",
    "test_segment_targeting": "Segments",
    "test_onsite_frequency_cap": "Notifications",
    "test_survey_submission": "Surveys",
}

# Where the module-level area is wrong for one test. Kept short on purpose: a
# long list here means the modules are organised badly.
TEST_AREA_OVERRIDES: dict[str, str] = {
    # Lives with the contacts error states because it is the same technique,
    # but it is the analytics screen that must degrade.
    "test_a_failing_analytics_request_shows_an_error_page": "Analytics",
}

# Fallback feature for modules with no @allure.feature of their own — the BDD
# modules, which are generated from .feature files.
MODULE_FEATURES: dict[str, str] = {
    "test_campaign_lifecycle": "Campaign lifecycle (journey)",
    "test_segment_targeting": "Segment targeting (journey)",
    "test_onsite_frequency_cap": "Frequency capping (journey)",
    "test_survey_submission": "Survey responses (journey)",
    "test_tenant_isolation": "Tenant isolation",
}

# --- severity --------------------------------------------------------------
#
# Four levels actually used. A severity chart where every bar is the same
# colour carries no information, so the question asked for each module is
# "what happens to the business if this breaks", not "how much do I like this
# test".
#
#   blocker   nobody can use the product, or one tenant can read another's data
#   critical  a core promise is broken — wrong audience, duplicate send, wrong numbers
#   normal    a feature misbehaves; the product still works
#   minor     wording and presentation

MODULE_SEVERITY: dict[str, str] = {
    # blocker — authentication, and the tenant boundary
    "test_auth": "blocker",
    "test_tenant_isolation": "blocker",
    "test_login": "blocker",
    # critical — the promises that cost money or trust when broken
    "test_rbac": "critical",
    "test_rbac_ui": "critical",
    "test_delivery_idempotency": "critical",
    "test_analytics_invariants": "critical",
    "test_segments_rules": "critical",
    "test_campaign_states": "critical",
    "test_campaign_lifecycle": "critical",
    "test_segment_targeting": "critical",
    # normal — a feature misbehaves
    "test_contacts_crud": "normal",
    "test_contacts_pagination": "normal",
    "test_contacts_grid": "normal",
    "test_error_states": "normal",
    "test_analytics_data": "normal",
    "test_seed_data": "normal",
    "test_contract_openapi": "normal",
    # The guard exists to prevent an irreversible loss of the live demo.
    "test_reset_guard": "blocker",
    # Data filed under the wrong tenant, or retained after deletion.
    "test_storage_facts": "critical",
    "test_onsite_frequency_cap": "normal",
    "test_survey_submission": "normal",
}

# Tests whose subject is wording rather than behaviour. Being wrong here is
# embarrassing, not broken.
MINOR_TESTS: frozenset[str] = frozenset({
    "test_a_refused_transition_explains_itself",
    "test_an_invalid_login_shows_an_error",
})

# --- links to known defects ------------------------------------------------

DEFECTS_BASE = (
    "https://github.com/mohammad-faisal-qa/engage-test-automation/blob/main/docs/defects"
)

DEFECTS: dict[str, str] = {
    "DEF-001": f"{DEFECTS_BASE}/DEF-001-delete-contact-with-deliveries-returns-500.md",
    "DEF-002": f"{DEFECTS_BASE}/DEF-002-viewer-reaches-edit-route.md",
    "DEF-003": f"{DEFECTS_BASE}/DEF-003-sticky-wait-always-succeeds.md",
    "DEF-004": f"{DEFECTS_BASE}/DEF-004-ci-only-connection-reset.md",
    "DEF-005": f"{DEFECTS_BASE}/DEF-005-unverified-database-endpoints.md",
}

# A failure in one of these is one click from the report that explains it.
MODULE_DEFECTS: dict[str, tuple[str, ...]] = {
    # The guard was written because of DEF-005; a failure here is that defect.
    "test_reset_guard": ("DEF-005",),
    # Their cleanup provokes DEF-001, and DEF-004 was that defect seen from
    # the other end — these are the tests it errored.
    "test_delivery_idempotency": ("DEF-001", "DEF-004"),
}

TEST_DEFECTS: dict[str, tuple[str, ...]] = {
    "test_a_contact_with_deliveries_cannot_be_deleted": ("DEF-001",),
    "test_a_viewer_reaching_the_edit_route_directly_cannot_save": ("DEF-002",),
    # The three that caught, or would have caught, the sticky wait.
    "test_paging_controls_move_and_stop_at_the_ends": ("DEF-003",),
    "test_the_back_button_returns_to_the_previous_grid_state": ("DEF-003",),
    "test_changing_the_page_size_changes_the_rows_shown": ("DEF-003",),
}

# --- derivation ------------------------------------------------------------

_LAYER_BY_MARKER = (
    ("db", "Database"),
    ("unit", "Unit"),
    ("contract", "Contract"),
    ("e2e", "Journey"),
    ("ui", "Browser"),
    ("api", "API"),
)


def layer_for(markers: set[str]) -> str:
    """Which layer a test belongs to, most specific marker first."""
    for marker, layer in _LAYER_BY_MARKER:
        if marker in markers:
            return layer
    return "Other"


# Some modules are parametrised *by product area* without saying so: the
# contract tests run per model, and the seed tests per pinned constant. Reading
# the parameter puts each one under the area it is actually about, instead of
# piling 36 tests into a "Platform" bucket that tells a reader nothing.
PARAM_AREAS: dict[str, str] = {
    # contract models
    "ContactOut": "Contacts",
    "SegmentOut": "Segments",
    "CampaignOut": "Campaigns",
    "DeliveryOut": "Delivery",
    "CampaignStats": "Analytics",
    # pinned seed constants
    "ACME_CONTACT_ID": "Contacts",
    "GLOBEX_CONTACT_ID": "Contacts",
    "SEGMENT_ENTERPRISE_RULE": "Segments",
    "SEGMENT_HIGH_VALUE_RULE": "Segments",
    "SEGMENT_VIP_STATIC": "Segments",
    "SEGMENT_GLOBEX_FREE": "Segments",
    "CAMPAIGN_DRAFT": "Campaigns",
    "CAMPAIGN_SCHEDULED": "Campaigns",
    "CAMPAIGN_SENT": "Campaigns",
    "CAMPAIGN_GLOBEX_DRAFT": "Campaigns",
    "CAMPAIGN_GLOBEX_RUNNING": "Campaigns",
}


def area_for(module: str, test_name: str, params: dict | None = None) -> str:
    if test_name in TEST_AREA_OVERRIDES:
        return TEST_AREA_OVERRIDES[test_name]
    for value in (params or {}).values():
        if isinstance(value, str) and value in PARAM_AREAS:
            return PARAM_AREAS[value]
    return MODULE_AREAS.get(module, "Platform")


def severity_for(module: str, test_name: str) -> str:
    if test_name in MINOR_TESTS:
        return "minor"
    return MODULE_SEVERITY.get(module, "normal")


def defects_for(module: str, test_name: str) -> tuple[str, ...]:
    return TEST_DEFECTS.get(test_name) or MODULE_DEFECTS.get(module, ())


def sentence_for(test_name: str) -> str:
    """`test_a_wrong_password_is_rejected` -> `A wrong password is rejected`.

    The suite already names its tests as sentences, so this only has to undo
    the syntax Python required. Where a name is not a sentence, the fix belongs
    in the test name rather than in a lookup table here.
    """
    words = re.sub(r"^test_", "", test_name).replace("_", " ").strip()
    return words[:1].upper() + words[1:] if words else test_name


def title_template(test_name: str, parameters: list[str]) -> str:
    """A readable title, keeping parametrised values visible.

    Allure substitutes `{name}` placeholders from the test's parameters, and it
    has to: every parametrisation of a function shares one function object, so a
    fixed title would render six identical rows and a reader could not tell
    which special character failed.
    """
    title = sentence_for(test_name)
    if not parameters:
        return title
    shown = parameters[:2]
    return title + " [" + ", ".join("{" + name + "}" for name in shown) + "]"
