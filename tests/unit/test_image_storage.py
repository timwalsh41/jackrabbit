"""Unit tests for app-managed image storage (JRB-027).

Pasted screenshot files live under ``{DATA_DIR}/uploads/`` with generated
names (random UUID + a magic-byte-derived extension). Nothing deletes them:
uploads are retained even when the referencing ticket is deleted.
"""

import re
from pathlib import Path

import pytest
from jackrabbit.image_storage import (
    ImageNotFoundError,
    ImageStorage,
    OversizedImageError,
    UnsupportedImageError,
)

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 16
GIF_BYTES = b"GIF89a" + b"\x00" * 16
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 16


class TestSave:
    def test_save_png_returns_url_and_writes_file(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        saved = storage.save(PNG_BYTES)
        assert saved.url == f"/images/{saved.name}"
        assert saved.name.endswith(".png")
        assert saved.content_type == "image/png"
        assert saved.size == len(PNG_BYTES)
        assert (tmp_path / "uploads" / saved.name).read_bytes() == PNG_BYTES

    def test_generated_name_is_a_random_uuid_hex(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        first = storage.save(PNG_BYTES)
        second = storage.save(PNG_BYTES)
        # Generated names, not user filenames: two identical uploads get two
        # distinct UUID-based names.
        assert first.name != second.name
        assert re.fullmatch(r"[0-9a-f]{32}\.png", first.name)

    def test_extension_follows_magic_bytes_not_client_filename(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        for data, ext, media in [
            (PNG_BYTES, ".png", "image/png"),
            (JPEG_BYTES, ".jpg", "image/jpeg"),
            (GIF_BYTES, ".gif", "image/gif"),
            (WEBP_BYTES, ".webp", "image/webp"),
        ]:
            saved = storage.save(data)
            assert saved.name.endswith(ext)
            assert saved.content_type == media

    def test_save_creates_uploads_dir_on_first_use(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        assert not (tmp_path / "uploads").exists()
        storage.save(PNG_BYTES)
        assert (tmp_path / "uploads").is_dir()

    def test_oversized_image_is_rejected_and_not_written(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        with pytest.raises(OversizedImageError):
            storage.save(PNG_BYTES + b"\x00" * (10 * 1024 * 1024))
        assert not (tmp_path / "uploads").exists()

    def test_unsupported_magic_bytes_are_rejected(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        with pytest.raises(UnsupportedImageError):
            storage.save(b"definitely not an image")
        with pytest.raises(UnsupportedImageError):
            # BMP magic bytes: not in the accepted set.
            storage.save(b"BM" + b"\x00" * 30)
        assert list((tmp_path / "uploads").glob("*")) == []

    def test_empty_upload_is_rejected(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        with pytest.raises(UnsupportedImageError):
            storage.save(b"")


class TestResolve:
    def test_resolve_returns_path_and_media_type(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        saved = storage.save(PNG_BYTES)
        path, media_type = storage.resolve(saved.name)
        assert path == (tmp_path / "uploads" / saved.name)
        assert media_type == "image/png"

    def test_resolve_rejects_traversal_and_separators(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        for bad in ("../jackrabbit.db", "a/b.png", ".", "..", "", "x\\y.png"):
            with pytest.raises(ImageNotFoundError):
                storage.resolve(bad)

    def test_resolve_rejects_unknown_names(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        with pytest.raises(ImageNotFoundError):
            storage.resolve("0123456789abcdef0123456789abcdef.png")

    def test_resolve_never_serves_outside_uploads_dir(self, tmp_path: Path):
        storage = ImageStorage(tmp_path)
        (tmp_path / "secret.txt").write_text("private")
        for bad in ("secret.txt", "..%2fsecret.txt"):
            with pytest.raises(ImageNotFoundError):
                storage.resolve(bad)
