"""Steps shared by every journey.

Two things live here and nothing else: the identity a journey is performed as,
and the scratch space a journey carries between its steps.

Everything in this package obeys one rule — **Gherkin describes outcomes, not
mechanics**. "Then the campaign is delivered to everyone in the segment" is a
statement a marketing manager could confirm or deny. "Then I click Send" is a
statement about a button, and it stops being true the moment the button moves.
That distinction is the entire reason for the translation layer; a feature file
written in mechanics is a slower, less readable version of the pytest test it
should have been.

Setup is performed through the API clients, never the interface. A journey about
frequency capping should fail when capping breaks — not when the form that
creates a notification breaks, which is a different test's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from pytest_bdd import given, parsers


@dataclass
class Journey:
    """State a scenario accumulates as it runs.

    A dataclass rather than a dict so a typo is an AttributeError at the step
    that made it, instead of a KeyError three steps later in an unrelated one.
    """

    role: str = "admin"
    tenant: str = "acme"

    # Records the journey created, kept so later steps can refer to "the
    # segment" or "the campaign" the way the feature file does.
    contacts: list[Any] = field(default_factory=list)
    segment: Any = None
    campaign: Any = None
    notification: Any = None
    survey: Any = None
    deliveries: list[Any] = field(default_factory=list)
    response: Any = None
    outcome: Any = None

    # Isolates a journey's own customers from every other journey's, so
    # segments resolve to exactly what this scenario created.
    marker: str | None = None
    # What a tenant-isolation journey asked for, so the follow-up step can ask
    # the same question as the rightful owner.
    record: Any = None

    @property
    def contact_ids(self) -> list[int]:
        return [contact.id for contact in self.contacts]


@pytest.fixture
def journey() -> Journey:
    return Journey()


@given(parsers.parse('I am signed in as the {role} of "{tenant}"'))
def signed_in_as(journey: Journey, role: str, tenant: str) -> None:
    """Establish who is acting.

    Only the identity is recorded; no client is built yet. Which client a step
    needs depends on what that step does, and resolving them lazily keeps this
    step from caring about a service list that grows every phase.
    """
    journey.role = role
    journey.tenant = tenant
