"""What each role can see and reach in the interface.

Hiding a control is a courtesy, not a security boundary — the API is the
boundary, and the API tests cover it. What these tests establish is that the two
agree: that the interface does not offer an action the server will refuse, and,
more importantly, that reaching past the interface does not get you anything.
"""

import allure
import pytest

from data.constants import SEGMENT_ENTERPRISE_RULE
from pages.contacts_page import ContactsPage
from pages.segments_page import SegmentsPage

pytestmark = [pytest.mark.ui]


@allure.feature("Authorisation in the UI")
@allure.story("A viewer is offered no write controls")
def test_a_viewer_sees_no_write_controls(page_as, settings):
    """Both halves in one test, deliberately.

    Asserting only that a viewer sees no buttons would pass just as well against
    a grid that failed to render at all. The admin context is the control that
    makes the viewer's absence mean something.
    """
    admin = ContactsPage(page_as("admin"), settings)
    admin.open_with(size=10)
    admin.grid.expect_loaded()
    first_id = admin.grid.row_ids()[0]

    with allure.step("An admin is offered the write controls"):
        admin.expect_visible(admin.new_button)
        admin.expect_visible(admin.edit_button(first_id))
        admin.expect_visible(admin.delete_button(first_id))

    viewer = ContactsPage(page_as("viewer"), settings)
    viewer.open_with(size=10)
    viewer.grid.expect_loaded()

    with allure.step("A viewer sees the same rows and none of the controls"):
        assert viewer.grid.row_ids() == admin.grid.row_ids(), (
            "the viewer sees different data, so this is not the same grid"
        )
        viewer.expect_count(viewer.new_button, 0)
        viewer.expect_count(viewer.edit_button(first_id), 0)
        viewer.expect_count(viewer.delete_button(first_id), 0)


@allure.feature("Authorisation in the UI")
@allure.story("An editor may edit but not delete")
def test_an_editor_is_offered_editing_but_not_deletion(page_as, settings):
    """The boundary between two permitted-looking actions, which is the one most
    easily got wrong: it is far easier to remember that viewers cannot write than
    that editors cannot destroy.
    """
    editor = ContactsPage(page_as("editor"), settings)
    editor.open_with(size=10)
    editor.grid.expect_loaded()
    first_id = editor.grid.row_ids()[0]

    editor.expect_visible(editor.new_button)
    editor.expect_visible(editor.edit_button(first_id))
    editor.expect_count(editor.delete_button(first_id), 0)


@allure.feature("Authorisation in the UI")
@allure.story("Reaching an edit route directly still cannot write")
def test_a_viewer_reaching_the_edit_route_directly_cannot_save(page_as, settings, api):
    """The test that matters, because it goes around the interface.

    The list hides the Edit link from a viewer, but the editor is a route and a
    route can be typed. So this asks the question that actually counts: having
    reached the form, can a viewer change anything?

    They cannot — the API refuses and the form says so. Note what this test is
    careful *not* to assert: that the route is blocked. It is not, and asserting
    otherwise would be encoding a wish rather than the behaviour. The
    client-side gap is real but it is a defence-in-depth observation, not a
    vulnerability, precisely because this assertion holds.
    """
    viewer = SegmentsPage(page_as("viewer"), settings)
    before = api.segments().get_one(SEGMENT_ENTERPRISE_RULE)

    with allure.step(f"Type the editor URL for segment {SEGMENT_ENTERPRISE_RULE}"):
        viewer.open_editor(SEGMENT_ENTERPRISE_RULE)

    with allure.step("Attempt to rename it"):
        viewer.name_input.fill("renamed by a viewer")
        viewer.save_button.click()

    with allure.step("The server refuses and the form reports it"):
        viewer.expect_visible(viewer.error)

    after = api.segments().get_one(SEGMENT_ENTERPRISE_RULE)
    assert after.name == before.name, (
        f"a viewer renamed segment {SEGMENT_ENTERPRISE_RULE} from {before.name!r} "
        f"to {after.name!r} by going directly to the edit route"
    )
