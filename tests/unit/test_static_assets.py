"""Every asset the SSR templates reference must be served locally.

The app is a local-first single-user tool (ADR-0001, ADR-0004), so page loads
must not depend on any third-party CDN. This used to break silently: the
Tailwind URL in ``base.html`` 404'd (``tailwindcss@3`` ships no
``dist/tailwind.min.css``), and because the DOM/text e2e suite never looked at
computed style, 45/45 tests stayed green while the entire UI rendered unstyled.

These tests are the tripwire for both halves of that failure: no external
asset URLs, and the local files actually exist and are non-trivial.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = REPO_ROOT / "jackrabbit" / "templates"
STATIC_DIR = REPO_ROOT / "jackrabbit" / "static"

# src="..." / href="..." with a literal (non-Jinja) value
ASSET_ATTR = re.compile(r'\b(?:src|href)="([^"{}]+)"')
EXTERNAL = re.compile(r"^(?:https?:)?//", re.IGNORECASE)


def _selector(token: str) -> str:
    """Return the CSS selector Tailwind emits for a utility class name.

    Tailwind backslash-escapes CSS-special characters, so the template class
    ``min-h-[300px]`` is looked up in the stylesheet as ``.min-h-\\[300px\\]``.
    """
    escaped = ""
    for ch in token:
        escaped += f"\\{ch}" if ch in r":/.[%]" else ch
    return f".{escaped}"


def _template_attrs() -> list[tuple[Path, str]]:
    return [
        (f, url)
        for f in sorted(TEMPLATES_DIR.glob("*.html"))
        for url in ASSET_ATTR.findall(f.read_text())
    ]


class TestNoExternalAssets:
    def test_templates_reference_only_local_assets(self) -> None:
        offenders = [
            f"{f.name}: {url}"
            for f, url in _template_attrs()
            if EXTERNAL.match(url) or url.startswith("data:text/html")
        ]
        assert offenders == [], f"templates must not load third-party assets: {offenders}"

    def test_no_cdn_hostnames_anywhere_in_templates(self) -> None:
        cdn_hosts = ("unpkg.com", "cdn.jsdelivr.net", "cdnjs.cloudflare.com", "cdn.tailwindcss.com")
        hits = [
            f"{f.name}: {host}"
            for f in TEMPLATES_DIR.glob("*.html")
            for host in cdn_hosts
            if host in f.read_text()
        ]
        assert hits == [], f"CDN references found: {hits}"


class TestStaticAssetsExist:
    @pytest.mark.parametrize(
        ("path", "needle"),
        [
            ("/static/css/tailwind.css", ".btn-primary"),
            ("/static/css/app.css", "htmx-indicator"),
            ("/static/vendor/htmx.min.js", "htmx"),
            ("/static/vendor/htmx-json-enc.js", "json-enc"),
            ("/static/js/sprint-dropdown.js", "sprint"),
            ("/static/img/favicon.svg", "<svg"),
        ],
    )
    def test_referenced_asset_is_served(self, path: str, needle: str) -> None:
        asset = STATIC_DIR / path.removeprefix("/static/")
        assert asset.is_file(), f"missing local asset {asset}"
        # A failed download leaves an HTML error page behind; catch that here.
        text = asset.read_text(encoding="utf-8", errors="replace")
        assert not text.lstrip().startswith(("<!DOCTYPE", "<html")), (
            f"{asset} is not an asset (looks like HTML)"
        )
        assert needle in text, f"{asset} does not look like the expected library (no {needle!r})"

    def test_all_static_urls_in_templates_resolve(self) -> None:
        unresolved = [
            f"{f.name}: {url}"
            for f, url in _template_attrs()
            if url.startswith("/static/")
            and not (STATIC_DIR / url.removeprefix("/static/")).is_file()
        ]
        assert unresolved == [], f"templates reference non-existent static files: {unresolved}"


class TestTailwindBuildIsCurrent:
    """The committed stylesheet is a build artifact: keep it purged, non-empty
    and in sync with the templates that motivated it."""

    CSS = STATIC_DIR / "css" / "tailwind.css"

    def test_stylesheet_is_non_trivial(self) -> None:
        assert self.CSS.is_file(), (
            "run `make build-css` to (re)generate jackrabbit/static/css/tailwind.css"
        )
        assert self.CSS.stat().st_size > 5_000, "purged stylesheet suspiciously small"

    def test_utility_classes_used_by_templates_are_generated(self) -> None:
        css = self.CSS.read_text()
        for selector in (
            ".bg-indigo-600",
            ".hover\\:bg-indigo-700",
            ".max-w-7xl",
            ".rounded-full",
            ".btn{",
            ".btn-primary{",
            ".btn-outline{",
            ".btn-sm{",
        ):
            assert selector in css, (
                f"{selector} missing from the built stylesheet — rebuild with `make build-css`"
            )

    def test_stylesheet_covers_every_class_in_template_class_attributes(self) -> None:
        """Fail when a template introduces a Tailwind utility the build missed."""
        css = self.CSS.read_text()
        tokens: set[str] = set()
        for template in TEMPLATES_DIR.glob("*.html"):
            for attr in re.findall(r'class="([^"]*)"', template.read_text()):
                tokens.update(attr.split())
        # Drop Jinja fragments and non-Tailwind custom classes.
        utility = re.compile(
            r"^(?:[a-z-]+:)*(?:bg|text|border|rounded|flex|grid|hidden|inline|items|justify|px|py|p|m|w|h|gap|shadow|font|space|absolute|relative|top|left|right|bottom|z|opacity|transition|duration|col|row|min|max|overflow|table|divide|ring|cursor|select|whitespace|truncate|uppercase|leading|tracking|sticky|block|underline|italic|pointer|order)-"
        )
        missing = sorted(
            t for t in tokens if utility.match(t) and "{" not in t and _selector(t) not in css
        )
        assert missing == [], (
            f"classes in templates missing from CSS (rebuild `make build-css`): {missing}"
        )
