"""Tests for the testing infrastructure itself (ticket 13).

Verifies the shared fixtures in tests/conftest.py (test_settings, test_db,
client, seeded_projects, seeded_tickets) and the chrome-devtools-axi helper
in tests/cdx_helper.py behave as specified.
"""

import subprocess
import tempfile
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from tests import cdx_helper
from tests.cdx_helper import ChromeDevToolsAxi, chrome_devtools_axi


class TestTestSettings:
    """test_settings overrides DATA_DIR to a temp dir and PORT to 0."""

    def test_data_dir_is_temp_dir(self, test_settings) -> None:
        assert test_settings.data_dir != Path("./data")
        assert str(test_settings.data_dir).startswith(tempfile.gettempdir())
        assert test_settings.data_dir.exists()

    def test_port_is_zero_ephemeral(self, test_settings) -> None:
        assert test_settings.port == 0

    def test_environment_is_test(self, test_settings) -> None:
        assert test_settings.environment == "test"


class TestTestDb:
    """test_db provides a fresh SQLite database per test."""

    def test_db_is_in_memory_sqlite(self, test_db, test_settings) -> None:
        assert test_settings.database_url == "sqlite://"
        # Tables were created (migrations/schema applied)
        from jackrabbit.models import Project
        from sqlmodel import select

        projects = test_db.exec(select(Project)).all()
        assert projects == []


class TestClientFixture:
    """client is an httpx.AsyncClient pointed at http://test."""

    async def test_client_is_async_httpx(self, client) -> None:
        assert isinstance(client, httpx.AsyncClient)
        assert not isinstance(client, TestClient)
        assert str(client.base_url).rstrip("/") == "http://test"

    async def test_client_serves_the_app(self, client) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_client_uses_test_db(self, client, test_db) -> None:
        """Writes via the API are visible in the test_db session fixture."""
        response = await client.post(
            "/api/v1/projects",
            json={"prefix": "TST", "name": "Test Project"},
        )
        assert response.status_code == 201
        from jackrabbit.models import Project
        from sqlmodel import select

        projects = test_db.exec(select(Project)).all()
        assert any(p.prefix == "TST" for p in projects)


class TestSeededProjects:
    """seeded_projects creates UNS + 2 test projects."""

    def test_uns_plus_two_projects(self, seeded_projects) -> None:
        assert len(seeded_projects) == 3
        uns = seeded_projects[0]
        assert uns.prefix == "UNS"
        assert uns.is_system is True
        others = seeded_projects[1:]
        assert {p.prefix for p in others} == {"WEB", "API"}
        assert all(p.is_system is False for p in others)


class TestSeededTickets:
    """seeded_tickets creates tickets in various states."""

    def test_tickets_in_various_states(self, seeded_tickets) -> None:
        assert len(seeded_tickets) >= 4
        statuses = {t.status.value for t in seeded_tickets}
        assert len(statuses) >= 3, f"expected variety, got {statuses}"
        assert "Open" in statuses
        assert statuses != {"Open"}, "all tickets are Open; expected various states"


class TestChromeDevToolsAxi:
    """chrome-devtools-axi helper builds env, runs commands, and manages lifecycle."""

    def test_env_builder(self) -> None:
        bridge = ChromeDevToolsAxi(port=9333, session="test-session", headed=True)
        env = bridge._env()
        assert env["CHROME_DEVTOOLS_AXI_PORT"] == "9333"
        assert env["CHROME_DEVTOOLS_AXI_SESSION"] == "test-session"
        assert env["CHROME_DEVTOOLS_AXI_HEADED"] == "1"

    def test_run_command_parses_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bridge = ChromeDevToolsAxi(port=9333)
        bridge._bridge_ready = True

        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(cmd, 0, stdout='{"ok": true}', stderr="")

        monkeypatch.setattr(cdx_helper.subprocess, "run", fake_run)
        result = bridge.run_command("snapshot")
        assert result == {"ok": True}
        assert captured["cmd"] == ["chrome-devtools-axi", "snapshot"]

    def test_context_manager_starts_and_stops(self, monkeypatch: pytest.MonkeyPatch) -> None:
        events: list[str] = []

        def fake_start(self, timeout: int = 30000) -> None:
            events.append("start")

        def fake_stop(self) -> None:
            events.append("stop")

        monkeypatch.setattr(ChromeDevToolsAxi, "start", fake_start)
        monkeypatch.setattr(ChromeDevToolsAxi, "stop", fake_stop)

        with chrome_devtools_axi(port=9333) as bridge:
            assert isinstance(bridge, ChromeDevToolsAxi)

        assert events == ["start", "stop"]

    def test_fixture_helpers_are_importable(self) -> None:
        assert hasattr(cdx_helper, "cdx_bridge")
        assert hasattr(cdx_helper, "cdx_bridge_per_test")
        assert hasattr(cdx_helper, "CDXPageHelper")
