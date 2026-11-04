"""Integration tests for the criteria API: CRUD on /tickets/{id}/criteria,
the criteria list on the Groomed transition payload, verifier sign-off, and
the Complete guard (JRB-021/JRB-022, ADR-0025)."""

from httpx import AsyncClient


async def _story(client: AsyncClient, title: str = "Criteria ticket", type: str = "Story") -> dict:
    response = await client.post(
        "/api/v1/tickets", json={"project_id": 2, "title": title, "type": type}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add(client: AsyncClient, ticket_id: int, text: str):
    return await client.post(f"/api/v1/tickets/{ticket_id}/criteria", json={"text": text})


async def _groom(client: AsyncClient, ticket_id: int, **extra):
    payload = {
        "to_status": "Groomed",
        "reason": "ready",
        "approach": "Approach",
        "files_to_change": "files",
        "test_plan": "Plan",
        "validation_steps": "Steps",
    }
    payload.update(extra)
    return await client.post(f"/api/v1/tickets/{ticket_id}/transition", json=payload)


class TestCriteriaCrud:
    """POST/GET/PATCH/DELETE /api/v1/tickets/{id}/criteria while editable."""

    async def test_add_assigns_sequential_positions(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        first = await _add(client_with_seeds, ticket["id"], "It works")
        second = await _add(client_with_seeds, ticket["id"], "It is tested")
        assert first.status_code == 201
        assert first.json()["position"] == 0
        assert second.status_code == 201
        assert second.json()["position"] == 1
        assert second.json()["verified"] is False
        assert second.json()["verified_at"] is None

    async def test_add_rejects_blank_text(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        response = await _add(client_with_seeds, ticket["id"], "   ")
        assert response.status_code == 422
        assert "Criterion text is required" in response.json()["detail"]

    async def test_list_orders_by_position(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        first = (await _add(client_with_seeds, ticket["id"], "It is tested")).json()
        await _add(client_with_seeds, ticket["id"], "It works")
        await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{first['id']}", json={"position": 5}
        )
        response = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        assert response.status_code == 200
        assert [row["text"] for row in response.json()] == ["It works", "It is tested"]

    async def test_update_text(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        row = (await _add(client_with_seeds, ticket["id"], "It works")).json()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}", json={"text": "Revised"}
        )
        assert response.status_code == 200
        assert response.json()["text"] == "Revised"

    async def test_delete_removes_the_row(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        row = (await _add(client_with_seeds, ticket["id"], "It works")).json()
        response = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}"
        )
        assert response.status_code == 204
        remaining = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        assert remaining.json() == []

    async def test_unknown_ticket_is_404(self, client_with_seeds: AsyncClient):
        response = await client_with_seeds.get("/api/v1/tickets/9999/criteria")
        assert response.status_code == 404
        post = await _add(client_with_seeds, 9999, "It works")
        assert post.status_code == 404

    async def test_unknown_criterion_is_404(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        patch = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/9999", json={"text": "Nope"}
        )
        assert patch.status_code == 404
        delete = await client_with_seeds.delete(f"/api/v1/tickets/{ticket['id']}/criteria/9999")
        assert delete.status_code == 404


class TestCriteriaStatusGate:
    """Criteria are rejected from In Progress onward; allowed on Open/Groomed."""

    async def _in_progress_story(self, client_with_seeds: AsyncClient) -> dict:
        ticket = await _story(client_with_seeds)
        groomed = await _groom(client_with_seeds, ticket["id"], criteria=["It works"])
        assert groomed.status_code == 200, groomed.text
        started = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "In Progress"}
        )
        assert started.status_code == 200
        return ticket

    async def test_crud_works_on_a_groomed_ticket(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        groomed = await _groom(client_with_seeds, ticket["id"], criteria=["First"])
        assert groomed.status_code == 200
        added = await _add(client_with_seeds, ticket["id"], "Second")
        assert added.status_code == 201
        assert added.json()["position"] == 1

    async def test_crud_is_rejected_once_in_progress(self, client_with_seeds: AsyncClient):
        ticket = await self._in_progress_story(client_with_seeds)
        assert (await _add(client_with_seeds, ticket["id"], "Late")).status_code == 409
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        locked = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"text": "Rewrite"}
        )
        assert locked.status_code == 409
        delete = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}"
        )
        assert delete.status_code == 409

    async def _story_ready_for_review(self, client_with_seeds: AsyncClient) -> dict:
        ticket = await self._in_progress_story(client_with_seeds)
        review = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Ready for Review"},
        )
        assert review.status_code == 200
        return ticket

    async def test_crud_is_rejected_while_ready_for_review(self, client_with_seeds: AsyncClient):
        ticket = await self._story_ready_for_review(client_with_seeds)
        assert (await _add(client_with_seeds, ticket["id"], "Late")).status_code == 409
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        locked = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"text": "Rewrite"}
        )
        assert locked.status_code == 409
        delete = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}"
        )
        assert delete.status_code == 409

    async def test_crud_is_rejected_once_complete(self, client_with_seeds: AsyncClient):
        ticket = await self._story_ready_for_review(client_with_seeds)
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        for row in rows:
            signed = await client_with_seeds.patch(
                f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}",
                json={"verified": True},
            )
            assert signed.status_code == 200
        done = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "Complete"}
        )
        assert done.status_code == 200
        assert (await _add(client_with_seeds, ticket["id"], "Late")).status_code == 409
        locked = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"text": "Rewrite"}
        )
        assert locked.status_code == 409
        delete = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}"
        )
        assert delete.status_code == 409

    async def test_lock_message_explains_the_round_trip(self, client_with_seeds: AsyncClient):
        ticket = await self._in_progress_story(client_with_seeds)
        response = await _add(client_with_seeds, ticket["id"], "Late")
        assert "Groomed" in response.json()["detail"]


class TestCriteriaTransitionPayload:
    """The Groomed transition accepts a criteria list atomically."""

    async def test_grooming_with_criteria_persists_rows_in_order(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _story(client_with_seeds)
        response = await _groom(
            client_with_seeds, ticket["id"], criteria=["It works", "It is tested"]
        )
        assert response.status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        assert [row["text"] for row in rows] == ["It works", "It is tested"]
        assert [row["position"] for row in rows] == [0, 1]

    async def test_story_grooming_without_criteria_is_rejected(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _story(client_with_seeds)
        response = await _groom(client_with_seeds, ticket["id"])
        assert response.status_code == 400
        assert "acceptance criterion" in response.json()["detail"]
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Open"

    async def test_epic_grooms_without_criteria(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds, "Planning container", type="Epic")
        response = await _groom(client_with_seeds, ticket["id"])
        assert response.status_code == 200

    async def test_spike_grooms_with_no_fields_and_no_criteria(
        self, client_with_seeds: AsyncClient
    ):
        """ADR-0008 relaxation: a Spike needs neither groomed fields nor criteria."""
        ticket = await _story(client_with_seeds, "Research spike", type="Spike")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Groomed", "reason": "spike"},
        )
        assert response.status_code == 200
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Groomed"

    async def test_blank_criterion_in_payload_fails_atomically(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await _story(client_with_seeds)
        response = await _groom(client_with_seeds, ticket["id"], criteria=["Good", "   "])
        assert response.status_code == 400
        assert "Criterion text is required" in response.json()["detail"]
        # Nothing persisted: status unchanged, no criteria rows.
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Open"
        criteria = await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")
        assert criteria.json() == []

    async def test_re_grooming_replaces_the_criteria_list(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        assert (await _groom(client_with_seeds, ticket["id"], criteria=["Old"])).status_code == 200
        # Round-trip back to Open, then re-groom with a revised list.
        await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "Open"}
        )
        response = await _groom(client_with_seeds, ticket["id"], criteria=["New one", "New two"])
        assert response.status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        assert [row["text"] for row in rows] == ["New one", "New two"]


class TestCriteriaPrecheck:
    """GET /tickets/{id}/transition/can?to_status=Groomed reflects the gate."""

    async def test_story_without_criteria_fails_the_precheck(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        patched = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}",
            json={
                "approach": "Approach",
                "files_to_change": "files",
                "test_plan": "Plan",
                "validation_steps": "Steps",
            },
        )
        assert patched.status_code == 200
        response = await client_with_seeds.get(
            f"/api/v1/tickets/{ticket['id']}/transition/can", params={"to_status": "Groomed"}
        )
        assert response.json()["can_transition"] is False
        assert "acceptance criterion" in response.json()["error_message"]

        # Adding a criterion satisfies the gate.
        await _add(client_with_seeds, ticket["id"], "It works")
        response = await client_with_seeds.get(
            f"/api/v1/tickets/{ticket['id']}/transition/can", params={"to_status": "Groomed"}
        )
        assert response.json()["can_transition"] is True

    async def test_spike_passes_the_precheck_with_nothing(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds, "Spike precheck", type="Spike")
        response = await client_with_seeds.get(
            f"/api/v1/tickets/{ticket['id']}/transition/can", params={"to_status": "Groomed"}
        )
        assert response.json()["can_transition"] is True


class TestCriteriaSignoff:
    """PATCH /tickets/{id}/criteria/{cid} with {"verified": ...} flips the
    sign-off state; allowed only while In Progress or Ready for Review."""

    async def _story_in_progress(self, client: AsyncClient) -> dict:
        ticket = await _story(client)
        groomed = await _groom(client, ticket["id"], criteria=["It works", "It is tested"])
        assert groomed.status_code == 200, groomed.text
        started = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "In Progress"}
        )
        assert started.status_code == 200
        return ticket

    async def test_sign_off_flips_verified_with_timestamp(self, client_with_seeds: AsyncClient):
        ticket = await self._story_in_progress(client_with_seeds)
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"verified": True}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["verified"] is True
        assert body["verified_at"] is not None
        # The other criterion is untouched.
        remaining = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        assert remaining[1]["verified"] is False

    async def test_unverify_clears_the_timestamp(self, client_with_seeds: AsyncClient):
        ticket = await self._story_in_progress(client_with_seeds)
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        cid = rows[0]["id"]
        assert (
            await client_with_seeds.patch(
                f"/api/v1/tickets/{ticket['id']}/criteria/{cid}", json={"verified": True}
            )
        ).status_code == 200
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{cid}", json={"verified": False}
        )
        assert response.status_code == 200
        assert response.json()["verified"] is False
        assert response.json()["verified_at"] is None

    async def test_sign_off_is_allowed_while_ready_for_review(self, client_with_seeds: AsyncClient):
        ticket = await self._story_in_progress(client_with_seeds)
        review = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Ready for Review", "pr_url": "https://github.com/o/r/pull/1"},
        )
        assert review.status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"verified": True}
        )
        assert response.status_code == 200

    async def test_sign_off_is_rejected_while_open(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        row = (await _add(client_with_seeds, ticket["id"], "It works")).json()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}", json={"verified": True}
        )
        assert response.status_code == 409
        assert "signed off" in response.json()["detail"]

    async def test_sign_off_is_rejected_while_groomed(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        assert (
            await _groom(client_with_seeds, ticket["id"], criteria=["It works"])
        ).status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"verified": True}
        )
        assert response.status_code == 409
        assert "signed off" in response.json()["detail"]

    async def test_sign_off_is_rejected_once_complete(self, client_with_seeds: AsyncClient):
        ticket = await self._story_in_progress(client_with_seeds)
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        cid = rows[0]["id"]
        for row in rows:
            assert (
                await client_with_seeds.patch(
                    f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}",
                    json={"verified": True},
                )
            ).status_code == 200
        review = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Ready for Review"},
        )
        assert review.status_code == 200
        done = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "Complete"}
        )
        assert done.status_code == 200
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{cid}", json={"verified": False}
        )
        assert response.status_code == 409

    async def test_sign_off_is_rejected_once_rejected(self, client_with_seeds: AsyncClient):
        ticket = await self._story_in_progress(client_with_seeds)
        rejected = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "Rejected"}
        )
        assert rejected.status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"verified": True}
        )
        assert response.status_code == 409
        assert "signed off" in response.json()["detail"]

    async def test_sign_off_unknown_criterion_is_404(self, client_with_seeds: AsyncClient):
        ticket = await self._story_in_progress(client_with_seeds)
        response = await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/9999", json={"verified": True}
        )
        assert response.status_code == 404


class TestCompleteGuardApi:
    """Ready for Review -> Complete fails while any criterion is unverified;
    Spike and zero-criterion tickets are exempt (ADR-0025)."""

    async def _story_ready_for_review(self, client: AsyncClient, type: str = "Story") -> dict:
        ticket = await _story(client, type=type)
        if type in ("Story", "Bug"):
            groomed = await _groom(client, ticket["id"], criteria=["It works"])
            assert groomed.status_code == 200, groomed.text
        else:
            groomed = await client.post(
                f"/api/v1/tickets/{ticket['id']}/transition",
                json={"to_status": "Groomed", "reason": "ready"},
            )
            assert groomed.status_code == 200, groomed.text
        started = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "In Progress"}
        )
        assert started.status_code == 200
        review = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Ready for Review"},
        )
        assert review.status_code == 200
        return ticket

    async def test_complete_fails_while_a_criterion_is_unverified(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await self._story_ready_for_review(client_with_seeds)
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "Complete"}
        )
        assert response.status_code == 400
        assert "verified" in response.json()["detail"]
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Ready for Review"

    async def test_precheck_reflects_the_complete_guard(self, client_with_seeds: AsyncClient):
        ticket = await self._story_ready_for_review(client_with_seeds)
        response = await client_with_seeds.get(
            f"/api/v1/tickets/{ticket['id']}/transition/can", params={"to_status": "Complete"}
        )
        assert response.json()["can_transition"] is False
        assert "verified" in response.json()["error_message"]

    async def test_complete_passes_once_all_criteria_are_verified(
        self, client_with_seeds: AsyncClient
    ):
        ticket = await self._story_ready_for_review(client_with_seeds)
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        for row in rows:
            assert (
                await client_with_seeds.patch(
                    f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}",
                    json={"verified": True},
                )
            ).status_code == 200
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Complete", "reason": "merged"},
        )
        assert response.status_code == 200
        assert (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()[
            "status"
        ] == "Complete"

    async def test_spike_completes_without_any_criterion(self, client_with_seeds: AsyncClient):
        ticket = await self._story_ready_for_review(client_with_seeds, type="Spike")
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Complete", "reason": "report accepted"},
        )
        assert response.status_code == 200

    async def test_zero_criterion_ticket_completes(self, client_with_seeds: AsyncClient):
        """A ticket whose only row was removed while Groomed is exempt."""
        ticket = await _story(client_with_seeds)
        assert (
            await _groom(client_with_seeds, ticket["id"], criteria=["Temporary"])
        ).status_code == 200
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        delete = await client_with_seeds.delete(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}"
        )
        assert delete.status_code == 204
        started = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "In Progress"}
        )
        assert started.status_code == 200
        review = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Ready for Review"},
        )
        assert review.status_code == 200
        response = await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={"to_status": "Complete", "reason": "merged"},
        )
        assert response.status_code == 200


class TestCriteriaHistoryInDetail:
    """Adds, edits, and sign-offs each produce a history entry, exposed on
    the ticket detail payload with timestamp and criterion text (ADR-0025)."""

    async def _in_progress_story(self, client: AsyncClient) -> dict:
        ticket = await _story(client)
        groomed = await _groom(client, ticket["id"], criteria=["It works"])
        assert groomed.status_code == 200, groomed.text
        started = await client.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "In Progress"}
        )
        assert started.status_code == 200
        return ticket

    async def test_add_edit_signoff_produce_history_entries(self, client_with_seeds: AsyncClient):
        ticket = await _story(client_with_seeds)
        row = (await _add(client_with_seeds, ticket["id"], "It works")).json()
        await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{row['id']}", json={"text": "Revised"}
        )
        await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition",
            json={
                "to_status": "Groomed",
                "approach": "A",
                "files_to_change": "f",
                "test_plan": "P",
                "validation_steps": "V",
                "criteria": ["Revised"],
            },
        )
        await client_with_seeds.post(
            f"/api/v1/tickets/{ticket['id']}/transition", json={"to_status": "In Progress"}
        )
        # The Groomed replace re-created the rows: sign off the current one.
        rows = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}/criteria")).json()
        await client_with_seeds.patch(
            f"/api/v1/tickets/{ticket['id']}/criteria/{rows[0]['id']}", json={"verified": True}
        )

        detail = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()
        events = [(entry["event"], entry["text"]) for entry in detail["criteria_history"]]
        assert ("added", "It works") in events
        assert ("edited", "Revised") in events
        assert ("added", "Revised") in events
        assert ("verified", "Revised") in events
        assert all(entry["at"] for entry in detail["criteria_history"])

    async def test_detail_payload_carries_the_checklist_state(self, client_with_seeds: AsyncClient):
        ticket = await self._in_progress_story(client_with_seeds)
        detail = (await client_with_seeds.get(f"/api/v1/tickets/{ticket['id']}")).json()
        assert [c["text"] for c in detail["criteria"]] == ["It works"]
        assert detail["criteria"][0]["verified"] is False
        assert detail["criteria"][0]["verified_at"] is None
