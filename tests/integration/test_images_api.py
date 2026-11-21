"""Integration tests for clipboard-image upload and serving (JRB-027).

Covers the API-First contract for pasted ticket-description images:

- ``POST /api/v1/images`` (multipart) accepts PNG/JPEG/GIF/WebP up to 10 MiB
  and writes the file under the configured ``DATA_DIR/uploads/`` with a
  generated name; unsupported types and oversized payloads are rejected with
  a user-presentable ``detail``.
- ``GET /images/{name}`` serves stored uploads only.
- Saved references render as inline ``<img>`` in the ticket description and
  survive ticket deletion (uploads are never auto-deleted).

The client fixture mirrors ``client_with_seeds`` but points ``get_settings``
at a temp ``DATA_DIR`` so upload files land in a pytest temp dir instead of
the repo's ``./data`` (uploads resolve via ``Depends(get_settings)``).
"""

import re
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from jackrabbit.config import Settings, get_settings
from jackrabbit.main import create_app
from jackrabbit.services import ProjectService

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF_BYTES = b"GIF89a" + b"\x00" * 16
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16


@pytest.fixture
async def image_client(
    test_db,
    tmp_path: Path,
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """Seeded httpx client whose DATA_DIR (and thus /images storage) is tmp_path.

    Seeds the UNS system project: image-reference tests create tickets in
    project 1, and JRB-037 number allocation needs the project row to read
    and bump its ``next_number`` counter.
    """
    ProjectService(test_db).create_project(
        prefix="UNS",
        name="Unsorted",
        description="Default unsorted project",
        color="#9ca3af",
        is_system=True,
    )

    def get_test_session():
        yield test_db

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        environment="test",
        database_url="sqlite://",
        data_dir=tmp_path,
        port=0,
        log_level="DEBUG",
    )

    from jackrabbit.database import get_session

    app.dependency_overrides[get_session] = get_test_session

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(base_url="http://test", transport=transport) as async_client:
        yield async_client

    app.dependency_overrides.clear()


async def _upload(client: httpx.AsyncClient, data: bytes, filename: str, media: str):
    return await client.post(
        "/api/v1/images",
        files={"file": (filename, data, media)},
    )


class TestImageUpload:
    @pytest.mark.parametrize(
        ("data", "media", "expected_ext", "expected_content_type"),
        [
            (PNG_BYTES, "image/png", ".png", "image/png"),
            (JPEG_BYTES, "image/jpeg", ".jpg", "image/jpeg"),
            (GIF_BYTES, "image/gif", ".gif", "image/gif"),
            (WEBP_BYTES, "image/webp", ".webp", "image/webp"),
        ],
    )
    async def test_supported_formats_upload(
        self,
        image_client: httpx.AsyncClient,
        tmp_path: Path,
        data: bytes,
        media: str,
        expected_ext: str,
        expected_content_type: str,
    ) -> None:
        response = await _upload(image_client, data, f"paste{expected_ext}", media)
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["url"] == f"/images/{body['name']}"
        assert body["name"].endswith(expected_ext)
        assert body["size"] == len(data)
        assert body["content_type"] == expected_content_type
        # Stored under the configured DATA_DIR, in the uploads subdir, with a
        # generated (not client-supplied) name.
        assert (tmp_path / "uploads" / body["name"]).read_bytes() == data
        assert re.fullmatch(rf"[0-9a-f]{{32}}\{expected_ext}", body["name"])

    async def test_extension_derived_from_magic_bytes_not_filename(
        self, image_client: httpx.AsyncClient, tmp_path: Path
    ) -> None:
        response = await _upload(image_client, PNG_BYTES, "innocent.txt", "text/plain")
        assert response.status_code == 201, response.text
        assert response.json()["name"].endswith(".png")

    @pytest.mark.parametrize(
        ("data", "media"),
        [
            (b"definitely not an image", "image/png"),
            (b"BM" + b"\x00" * 30, "image/bmp"),
            (b"", "image/png"),
        ],
    )
    async def test_unsupported_images_are_rejected(
        self, image_client: httpx.AsyncClient, tmp_path: Path, data: bytes, media: str
    ) -> None:
        response = await _upload(image_client, data, "x.png", media)
        assert response.status_code == 400
        assert "detail" in response.json()
        assert list((tmp_path / "uploads").glob("*")) == []

    async def test_oversized_image_is_rejected(
        self, image_client: httpx.AsyncClient, tmp_path: Path
    ) -> None:
        oversized = PNG_BYTES + b"\x00" * (10 * 1024 * 1024)
        response = await _upload(image_client, oversized, "big.png", "image/png")
        assert response.status_code == 413
        assert "10 MiB" in response.json()["detail"]
        assert list((tmp_path / "uploads").glob("*")) == []

    async def test_image_at_exactly_the_limit_is_accepted(
        self, image_client: httpx.AsyncClient
    ) -> None:
        at_limit = PNG_BYTES + b"\x00" * (10 * 1024 * 1024 - len(PNG_BYTES))
        response = await _upload(image_client, at_limit, "max.png", "image/png")
        assert response.status_code == 201, response.text


class TestImageServing:
    async def test_stored_image_is_served(self, image_client: httpx.AsyncClient) -> None:
        saved = (await _upload(image_client, PNG_BYTES, "x.png", "image/png")).json()
        response = await image_client.get(saved["url"])
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("image/png")
        assert response.content == PNG_BYTES

    async def test_unknown_name_is_404(self, image_client: httpx.AsyncClient) -> None:
        response = await image_client.get("/images/0123456789abcdef0123456789abcdef.png")
        assert response.status_code == 404

    async def test_non_image_names_cannot_be_served(self, image_client: httpx.AsyncClient) -> None:
        for bad in ("/images/whatever.txt", "/images/../jackrabbit.db", "/images/x/y.png"):
            response = await image_client.get(bad)
            assert response.status_code == 404, bad


class TestImageReferencesInTickets:
    async def test_description_with_image_reference_renders_img(
        self, image_client: httpx.AsyncClient
    ) -> None:
        saved = (await _upload(image_client, PNG_BYTES, "x.png", "image/png")).json()
        created = await image_client.post(
            "/api/v1/tickets",
            json={
                "project_id": 1,
                "title": "Image reference ticket",
                "type": "Story",
                "description": f"Screenshot: ![shot]({saved['url']})",
            },
        )
        ticket_id = created.json()["id"]

        fields = await image_client.get(
            f"/tickets/{ticket_id}/fields", headers={"Accept": "text/html"}
        )
        assert fields.status_code == 200
        assert f'<img src="{saved["url"]}" alt="shot">' in fields.text

    async def test_uploads_survive_ticket_deletion(
        self, image_client: httpx.AsyncClient, tmp_path: Path
    ) -> None:
        saved = (await _upload(image_client, PNG_BYTES, "x.png", "image/png")).json()
        created = await image_client.post(
            "/api/v1/tickets",
            json={
                "project_id": 1,
                "title": "Doomed ticket",
                "type": "Story",
                "description": f"![shot]({saved['url']})",
            },
        )
        deleted = await image_client.delete(f"/api/v1/tickets/{created.json()['full_id']}")
        assert deleted.status_code == 204

        # Retention requirement: nothing removes the stored upload.
        assert (tmp_path / "uploads" / saved["name"]).is_file()
        served = await image_client.get(saved["url"])
        assert served.status_code == 200
        assert served.content == PNG_BYTES


class TestNonMultipartUploadRejected:
    def test_missing_file_field_is_422(self) -> None:
        """FastAPI's multipart contract: no file part means 422, not a crash."""
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: Settings(
            environment="test",
            database_url="sqlite://",
            data_dir=Path("./data"),
            port=0,
        )
        with TestClient(app) as client:
            response = client.post("/api/v1/images")
            assert response.status_code == 422
