"""Browser tests for inline acceptance-criteria editing (JRB-025)."""

import httpx
from playwright.sync_api import Page, expect


def _set_criteria(base_url: str, ticket_id: int, criteria: list[str]) -> None:
    with httpx.Client(base_url=base_url, timeout=30.0) as api:
        response = api.patch(f"/api/v1/tickets/{ticket_id}", json={"criteria": criteria})
        assert response.status_code == 200, response.text


def _criteria(base_url: str, ticket_id: int) -> list[dict]:
    with httpx.Client(base_url=base_url, timeout=30.0) as api:
        response = api.get(f"/api/v1/tickets/{ticket_id}/criteria")
        assert response.status_code == 200, response.text
        return response.json()


class TestInlineCriteriaEditor:
    def test_saving_empty_criteria_and_unchanged_list_succeeds(
        self, page: Page, base_url: str, make_ticket
    ):
        ticket = make_ticket(title="Clear acceptance criteria")
        ticket_id = ticket["id"]
        _set_criteria(base_url, ticket_id, ["Remove this criterion"])

        page.goto(f"{base_url}/tickets/{ticket_id}")
        page.wait_for_selector("#criteria-checklist .criterion-row", state="visible")
        page.locator("#criteria-section").get_by_role("button", name="Edit").click()
        editor = page.locator("#criteria-edit-form")
        editor.locator("[data-criteria-remove]").click()
        with page.expect_response(
            lambda response: (
                response.request.method == "PATCH"
                and response.url.endswith(f"/tickets/{ticket_id}/criteria")
            )
        ) as empty_save:
            editor.get_by_role("button", name="Save").click()
        assert empty_save.value.status == 200
        expect(page.locator("#criteria-section")).to_contain_text("No acceptance criteria yet")
        assert _criteria(base_url, ticket_id) == []

        # Saving an unchanged empty list must be a successful no-op, not an
        # omitted required JSON field.
        page.locator("#criteria-section").get_by_role("button", name="Edit").click()
        editor = page.locator("#criteria-edit-form")
        with page.expect_response(
            lambda response: (
                response.request.method == "PATCH"
                and response.url.endswith(f"/tickets/{ticket_id}/criteria")
            )
        ) as unchanged_save:
            editor.get_by_role("button", name="Save").click()
        assert unchanged_save.value.status == 200
        expect(page.locator("#criteria-section")).to_contain_text("No acceptance criteria yet")

    def test_edit_add_and_state_guidance(self, page: Page, base_url: str, make_ticket):
        ticket = make_ticket(title="Inline criteria controls")
        ticket_id = ticket["id"]
        _set_criteria(base_url, ticket_id, ["Original criterion", "Second criterion"])

        page.goto(f"{base_url}/tickets/{ticket_id}")
        page.wait_for_selector("#criteria-checklist .criterion-row", state="visible")
        section = page.locator("#criteria-section")
        expect(section).to_contain_text("Editable while Open or Groomed.")
        expect(section.get_by_role("button", name="Edit")).to_be_visible()
        expect(section.get_by_role("button", name="+ Add")).to_be_visible()
        assert section.evaluate("element => element.previousElementSibling.id") == (
            "ticket-fields-section"
        )

        section.get_by_role("button", name="Edit").click()
        editor = page.locator("#criteria-edit-form")
        expect(editor.locator("input[name='criteria']")).to_have_count(2)
        expect(editor.locator("input[name='criteria']").nth(0)).to_have_value("Original criterion")
        editor.locator("input[name='criteria']").nth(0).fill("Updated criterion")
        editor.get_by_role("button", name="Save").click()
        expect(page.locator("#criteria-checklist")).to_contain_text("Updated criterion")
        expect(page.locator("#criteria-checklist")).not_to_contain_text("Original criterion")

        page.locator("#criteria-section").get_by_role("button", name="+ Add").click()
        editor = page.locator("#criteria-edit-form")
        rows = editor.locator("input[name='criteria']")
        expect(rows).to_have_count(3)
        expect(rows.nth(2)).to_be_focused()
        rows.nth(2).fill("Added criterion")
        editor.get_by_role("button", name="Save").click()
        expect(page.locator("#criteria-checklist")).to_contain_text("Added criterion")
        assert [row["text"] for row in _criteria(base_url, ticket_id)] == [
            "Updated criterion",
            "Second criterion",
            "Added criterion",
        ]

        # Grooming keeps editing available and shows the editable-state note.
        page.get_by_role("button", name="Groomed →").click()
        groom_form = page.locator("#groom-form")
        groom_form.locator("[name='approach']").fill("Implementation approach")
        groom_form.locator("[name='files_to_change']").fill("module.py")
        groom_form.locator("[name='test_plan']").fill("Run the tests")
        groom_form.locator("[name='validation_steps']").fill("Verify the workflow")
        groom_form.get_by_role("button", name="Groom").click()
        expect(page.locator("#ticket-meta")).to_contain_text("Groomed", timeout=10000)
        section = page.locator("#criteria-section")
        expect(section).to_contain_text("Editable while Open or Groomed.")
        expect(section.get_by_role("button", name="Edit")).to_be_visible()
        expect(section.get_by_role("button", name="+ Add")).to_be_visible()
        section.get_by_role("button", name="Edit").click()
        groomed_editor = page.locator("#criteria-edit-form")
        expect(groomed_editor.locator("input[name='criteria']")).to_have_count(3)
        groomed_editor.get_by_role("button", name="Cancel").click()
        expect(page.locator("#criteria-section")).to_contain_text("Editable while Open or Groomed.")

        # Starting work locks the controls and changes the instruction.
        page.get_by_role("button", name="In Progress →").click()
        work_form = page.locator("#in-progress-form")
        work_form.locator("[name='branch_name']").fill("feature/criteria-editor")
        work_form.get_by_role("button", name="Start Work").click()
        expect(page.locator("#ticket-meta")).to_contain_text("In Progress", timeout=10000)
        section = page.locator("#criteria-section")
        expect(section).to_contain_text("Locked from In Progress - cycle back to Groomed to edit.")
        expect(section.get_by_role("button", name="Edit")).to_have_count(0)
        expect(section.get_by_role("button", name="+ Add")).to_have_count(0)

        # The UI permits a backward transition; returning to Groomed restores editing.
        page.once("dialog", lambda dialog: dialog.accept("Revise criteria"))
        page.get_by_role("button", name="← Groomed").click()
        expect(page.locator("#ticket-meta")).to_contain_text("Groomed", timeout=10000)
        section = page.locator("#criteria-section")
        expect(section).to_contain_text("Editable while Open or Groomed.")
        expect(section.get_by_role("button", name="Edit")).to_be_visible()
        expect(section.get_by_role("button", name="+ Add")).to_be_visible()

    def test_open_edit_form_allows_zero_criteria_but_grooming_still_requires_one(
        self, page: Page, base_url: str, make_ticket
    ):
        ticket = make_ticket(title="Optional while open")
        ticket_id = ticket["id"]

        page.goto(f"{base_url}/tickets/{ticket_id}/edit")
        criteria_field = page.locator(".criteria-field")
        expect(criteria_field.locator(".text-red-500")).to_have_count(0)
        expect(criteria_field.locator("input[name='criteria']")).not_to_have_attribute(
            "required", ""
        )
        page.locator("#title").fill("Saved without criteria")
        page.get_by_role("button", name="Save Changes").click()
        page.wait_for_url(f"**/tickets/{ticket_id}")
        assert _criteria(base_url, ticket_id) == []

        page.get_by_role("button", name="Groomed →").click()
        groom_form = page.locator("#groom-form")
        groom_form.locator("[name='approach']").fill("Implementation approach")
        groom_form.locator("[name='files_to_change']").fill("module.py")
        groom_form.locator("[name='test_plan']").fill("Run the tests")
        groom_form.locator("[name='validation_steps']").fill("Verify the workflow")
        groom_form.get_by_role("button", name="Groom").click()
        error = page.locator("#modal-error")
        expect(error).to_be_visible(timeout=10000)
        expect(error).to_contain_text("At least one acceptance criterion")
