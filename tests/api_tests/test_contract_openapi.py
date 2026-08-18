"""Contract tests against the application's own published OpenAPI document.

There is a trap in this idea worth naming, because it decides how the file is
built. FastAPI generates `/openapi.json` from the same Pydantic models it
serialises responses with. Validating a response against that document therefore
proves less than it looks: rename a field on `ContactOut` and *both* the response
and the schema change together, and a conformance check sails through. It is the
"agree by construction" problem the suite's own response models were written to
avoid, reappearing one level up.

So these tests do two different jobs, and only the second one catches a rename:

**Conformance** — live responses validate against what the document declares.
This catches a handler that bypasses its `response_model`, returns a bare
`JSONResponse`, or serialises a value the schema does not permit. Real drift, but
drift between two halves of the *application*.

**Consumer expectations** — the document still declares the fields, types and
enum values *this suite consumes*. That list lives here, in the consumer, and is
not derived from the app at all. It is the half that fails when the provider
renames something out from under its clients, which is the entire point of
writing a contract test rather than trusting a schema to check itself.

Everything here reads; nothing is created.
"""

import allure
import pytest
from jsonschema import Draft202012Validator

pytestmark = [pytest.mark.api, pytest.mark.contract, pytest.mark.readonly]


# The fields this suite actually reads, per model. Stated here rather than
# derived from the document, because a list derived from the provider would
# agree with the provider by definition and could never disagree with it.
CONSUMED_FIELDS: dict[str, set[str]] = {
    "ContactOut": {
        "id", "tenant_id", "email", "first_name", "last_name",
        "country", "plan", "attributes", "created_at",
    },
    "SegmentOut": {"id", "tenant_id", "name", "kind", "rules", "created_at"},
    "CampaignOut": {
        "id", "tenant_id", "name", "status", "channel", "segment_id", "created_at",
    },
    "DeliveryOut": {
        "id", "campaign_id", "contact_id", "status", "queued_at", "sent_at",
        "delivered_at", "opened_at", "clicked_at", "failed_at", "failed_reason",
    },
    "CampaignStats": {
        "campaign_id", "name", "status", "channel", "total", "sent", "delivered",
        "opened", "clicked", "failed", "delivery_rate", "open_rate", "click_rate",
    },
}

# Every value the suite is prepared to encounter. A provider adding a state is a
# breaking change for a consumer that branches on them, even though it breaks no
# schema — which is why this is asserted as an exact set, not a subset.
EXPECTED_ENUMS: dict[tuple[str, str], set[str]] = {
    ("CampaignOut", "status"): {"draft", "scheduled", "running", "sent"},
    ("CampaignOut", "channel"): {"email", "sms", "push", "onsite"},
    ("SegmentOut", "kind"): {"rule", "static"},
    ("DeliveryOut", "status"): {
        "queued", "sent", "delivered", "opened", "clicked", "failed",
    },
}

# Fields the contract declares but does not require, and is right not to: they
# carry a default, so the application may legitimately omit them. Listed
# explicitly so that "optional" is a decision recorded once rather than a gap
# nobody noticed — and so a field quietly *becoming* optional still fails.
OPTIONAL_BY_CONTRACT: set[tuple[str, str]] = {
    # attributes defaults to {} on the application model.
    ("ContactOut", "attributes"),
}

MODELS = sorted(CONSUMED_FIELDS)


def schema_for(openapi: dict, model: str) -> dict:
    schemas = openapi["components"]["schemas"]
    assert model in schemas, (
        f"the published contract no longer declares {model!r}. This suite reads "
        f"it, so either the model was renamed or the endpoint returning it is "
        f"gone. Declared models: {sorted(schemas)}"
    )
    return schemas[model]


def validator_for(openapi: dict, model: str) -> Draft202012Validator:
    """A validator whose `$ref`s resolve inside the whole OpenAPI document.

    OpenAPI 3.1 schemas *are* JSON Schema 2020-12, so no translation is needed —
    but a component schema alone cannot resolve `#/components/schemas/...`
    references. Handing the validator the entire document as its schema root,
    with a `$ref` at the top, gives those references a base to resolve against.
    """
    return Draft202012Validator({**openapi, "$ref": f"#/components/schemas/{model}"})


@allure.feature("Contract")
@allure.story("Every model this suite reads is still published")
@pytest.mark.parametrize("model", MODELS)
def test_the_contract_still_declares_the_models_this_suite_reads(openapi, model):
    schema_for(openapi, model)


@allure.feature("Contract")
@allure.story("Every field this suite reads is still declared and required")
@pytest.mark.parametrize("model", MODELS)
def test_the_fields_this_suite_reads_are_declared_and_required(openapi, model):
    """The assertion that survives a rename.

    A renamed field changes the response and the document together, so
    conformance still passes. What does not pass is this: the consumer's own list
    of what it needs, checked against what the provider now offers.

    Required, not merely present: a field that became optional is a field that
    can arrive missing, and every caller reading it would then break at runtime
    rather than here.
    """
    schema = schema_for(openapi, model)
    declared = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    consumed = CONSUMED_FIELDS[model]

    missing = consumed - declared
    assert not missing, (
        f"{model} no longer declares {sorted(missing)}, which this suite reads. "
        f"The field was renamed or removed in the application. "
        f"Declared now: {sorted(declared)}"
    )

    expected_required = {
        field for field in consumed if (model, field) not in OPTIONAL_BY_CONTRACT
    }
    optional = expected_required - required
    assert not optional, (
        f"{model} still declares {sorted(optional)} but no longer requires them, "
        f"so a response may omit them. Anything reading these fields would fail "
        f"at runtime instead of here."
    )


@allure.feature("Contract")
@allure.story("Enums are constrained to the values this suite handles")
@pytest.mark.parametrize(
    ("model", "field"), sorted(EXPECTED_ENUMS), ids=lambda v: str(v)
)
def test_enum_fields_are_constrained_to_the_expected_values(openapi, model, field):
    """Asserted as an exact set, in both directions.

    A removed value breaks code that produces it. An *added* value breaks code
    that consumes it — a campaign arriving in a state this suite has never heard
    of would fall through every branch that handles the four it knows. Neither
    direction violates the schema, which is precisely why the check belongs to
    the consumer.
    """
    schema = schema_for(openapi, model)
    declared_field = schema.get("properties", {}).get(field)
    assert declared_field is not None, f"{model}.{field} is no longer declared"

    values = declared_field.get("enum")
    assert values is not None, (
        f"{model}.{field} is no longer a constrained enum — it now accepts any "
        f"{declared_field.get('type', 'value')}, so a typo in the application "
        f"would be stored and served without complaint"
    )

    actual, expected = set(values), EXPECTED_ENUMS[(model, field)]
    assert actual == expected, (
        f"{model}.{field} values changed: "
        f"added {sorted(actual - expected) or 'nothing'}, "
        f"removed {sorted(expected - actual) or 'nothing'}"
    )


@allure.feature("Contract")
@allure.story("Live responses match the schema the application publishes")
@pytest.mark.parametrize("model", MODELS)
def test_live_responses_validate_against_their_declared_schema(
    openapi, live_responses, model
):
    """Conformance: what the application *sends* against what it *promises*.

    This is the half a schema can check about itself, and it is not nothing —
    it catches a handler that bypasses its response_model or hand-builds a
    JSONResponse, where the document and the wire genuinely can disagree.
    """
    instance = live_responses[model]
    errors = sorted(validator_for(openapi, model).iter_errors(instance), key=str)

    assert not errors, "\n".join(
        [f"{model} response does not match its declared schema:"]
        + [
            f"  {'.'.join(str(p) for p in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in errors
        ]
    )


@allure.feature("Contract")
@allure.story("Responses carry no fields the contract does not declare")
@pytest.mark.parametrize("model", MODELS)
def test_responses_carry_no_undeclared_fields(openapi, live_responses, model):
    """The check the suite's own models are deliberately unable to make.

    Those models tolerate unknown fields on purpose: adding one is backwards
    compatible, and a functional test has no business failing because the
    application grew a column. But *somebody* has to notice, because an
    undeclared field is a field no consumer was told about — and on these models
    it may well be one nobody meant to publish.

    Pydantic emits no `additionalProperties: false`, so JSON Schema validation
    will not catch this. It has to be asserted directly.
    """
    schema = schema_for(openapi, model)
    declared = set(schema.get("properties", {}))
    returned = set(live_responses[model])

    undeclared = returned - declared
    assert not undeclared, (
        f"{model} returned {sorted(undeclared)}, which the contract does not "
        f"declare. Either the field should be published, or it is internal and "
        f"should not be on the wire."
    )
