"""Pagination: the envelope, and that pages actually differ."""

import allure
import pytest

pytestmark = [pytest.mark.api, pytest.mark.smoke]

PAGE_SIZE = 5


@allure.feature("Contacts")
@allure.story("Paging returns a correct envelope and distinct pages")
def test_contacts_pagination_returns_a_correct_envelope(api):
    """Every assertion here is deliberately relative, never absolute.

    `total == 40` would be the obvious thing to write, and it passes — right up
    until this runs at `-n 4` and another worker inserts a contact between the
    two requests. The suite would then fail on a real system behaving correctly,
    which is the most expensive kind of failure because it trains people to
    rerun rather than to read.

    So: the envelope must echo what was asked for, a page must not exceed the
    size requested, page 2 must contain different records from page 1, and the
    total must be consistent with what was returned. All of those stay true no
    matter what anyone else is doing to the database at the same time.
    """
    contacts = api.contacts()

    with allure.step("Fetch page 1"):
        first = contacts.list(page=1, size=PAGE_SIZE)
    with allure.step("Fetch page 2"):
        second = contacts.list(page=2, size=PAGE_SIZE)

    # The envelope echoes the request.
    assert first.page == 1
    assert second.page == 2
    assert first.size == PAGE_SIZE
    assert second.size == PAGE_SIZE

    # A page never exceeds the size asked for.
    assert len(first.items) <= PAGE_SIZE
    assert len(second.items) <= PAGE_SIZE

    # The seed guarantees enough acme contacts to fill two pages of five;
    # nothing another worker does can reduce that.
    assert len(first.items) == PAGE_SIZE, "not enough seeded contacts to page through"
    assert len(second.items) == PAGE_SIZE

    # The point of paging: page 2 is a different slice, not a repeat of page 1.
    assert first.ids != second.ids
    assert not set(first.ids) & set(second.ids), (
        f"pages overlap: {sorted(set(first.ids) & set(second.ids))} appear on both, "
        f"so a caller walking the pages would see records twice"
    )

    # The total describes the whole collection, so it must be at least what two
    # pages have already produced. A relative check that cannot be broken by a
    # concurrent insert.
    assert first.total >= len(first.items) + len(second.items)

    # Everything returned belongs to the caller's tenant.
    assert {item.tenant_id for item in first.items} == {"acme"}
