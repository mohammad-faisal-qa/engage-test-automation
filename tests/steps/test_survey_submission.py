"""Steps for the survey submission journey."""

from __future__ import annotations

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from data.factories import contact_payload, unique_name

pytestmark = [pytest.mark.e2e, pytest.mark.api]

scenarios("../features/survey_submission.feature")

RATING_KEY = "satisfaction"


def create_survey(api, journey, *, low: int, high: int, status: str):
    surveys = api.surveys(role=journey.role, tenant=journey.tenant)
    survey = surveys.create(
        {
            "name": unique_name("Survey"),
            "questions": [
                {
                    "key": RATING_KEY,
                    "type": "rating",
                    "label": "How satisfied are you?",
                    "required": True,
                    "min": low,
                    "max": high,
                }
            ],
        }
    )
    response = surveys.update_response(survey.id, {"status": status})
    assert response.status_code == 200, response.text[:200]
    journey.survey = survey
    return survey


@given(parsers.parse("a running survey asking for a rating from {low:d} to {high:d}"))
def a_running_survey(journey, api, low, high):
    create_survey(api, journey, low=low, high=high, status="active")


@given(parsers.parse("a closed survey asking for a rating from {low:d} to {high:d}"))
def a_closed_survey(journey, api, low, high):
    create_survey(api, journey, low=low, high=high, status="closed")


@when(parsers.parse("a customer answers with a rating of {rating:d}"))
def a_customer_answers(journey, api, rating):
    """Records the outcome rather than asserting it — the same sentence serves
    the journey that succeeds and the two that are refused."""
    contact = api.contacts(role=journey.role, tenant=journey.tenant).create(
        contact_payload()
    )
    journey.contacts = [contact]
    journey.outcome = api.surveys(
        role=journey.role, tenant=journey.tenant
    ).submit_response(
        journey.survey.id,
        {"contact_id": contact.id, "answers": {RATING_KEY: rating}},
    )


@then("the response is recorded")
def the_response_is_recorded(journey):
    assert journey.outcome.status_code == 201, journey.outcome.text[:200]


@then("the answer is refused")
def the_answer_is_refused(journey):
    assert journey.outcome.status_code == 422, (
        f"an answer outside the survey's own range was accepted "
        f"({journey.outcome.status_code})"
    )


@then("the answer is refused because the survey is not running")
def refused_because_closed(journey):
    assert journey.outcome.status_code == 422
    assert "not accepting responses" in journey.outcome.text


@then(parsers.parse("the survey reports {count:d} response with an average rating of {average:f}"))
def the_survey_reports(journey, api, count, average):
    summary = api.surveys(role=journey.role, tenant=journey.tenant).summary(
        journey.survey.id
    )
    assert summary["total_responses"] == count
    rating = next(q for q in summary["questions"] if q["key"] == RATING_KEY)
    assert rating["average"] == pytest.approx(average)


@then("the survey reports no responses")
def the_survey_reports_nothing(journey, api):
    summary = api.surveys(role=journey.role, tenant=journey.tenant).summary(
        journey.survey.id
    )
    assert summary["total_responses"] == 0, (
        "a refused answer was stored anyway, so the summary is built on data "
        "the survey said it would not accept"
    )
