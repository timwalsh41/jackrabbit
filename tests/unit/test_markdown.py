"""Unit tests for the server-side markdown renderer (HTMX-safe)."""

import pytest
from jackrabbit.markdown import render_markdown


class TestMarkdownBasics:
    def test_empty_string_returns_empty(self):
        assert render_markdown("") == ""

    def test_plain_text_is_wrapped_in_paragraph(self):
        assert render_markdown("hello world") == "<p>hello world</p>"

    def test_heading_levels(self):
        assert render_markdown("# Title") == "<h1>Title</h1>"
        assert render_markdown("## Sub") == "<h2>Sub</h2>"
        assert render_markdown("### Deep") == "<h3>Deep</h3>"

    def test_bold(self):
        assert (
            render_markdown("this is **bold** text") == "<p>this is <strong>bold</strong> text</p>"
        )

    def test_italic(self):
        assert render_markdown("this is *italic* text") == "<p>this is <em>italic</em> text</p>"

    def test_inline_code(self):
        assert render_markdown("run `make test` now") == "<p>run <code>make test</code> now</p>"

    def test_link(self):
        html = render_markdown("see [docs](https://example.com)")
        assert '<a href="https://example.com"' in html
        assert ">docs</a>" in html

    def test_unordered_list(self):
        html = render_markdown("- one\n- two\n- three")
        assert "<ul>" in html
        assert html.count("<li>") == 3
        assert "<li>one</li>" in html

    def test_ordered_list(self):
        html = render_markdown("1. first\n2. second")
        assert "<ol>" in html
        assert "<li>first</li>" in html
        assert "<li>second</li>" in html

    def test_multiline_paragraph_becomes_single_block_with_br(self):
        html = render_markdown("line one\nline two")
        assert "<p>" in html
        assert "line one" in html
        assert "line two" in html

    def test_blank_line_starts_new_paragraph(self):
        html = render_markdown("first\n\nsecond")
        assert "<p>first</p>" in html
        assert "<p>second</p>" in html

    def test_code_block(self):
        html = render_markdown("```\ncode line\n```")
        assert "<pre><code>" in html
        assert "code line" in html


class TestMarkdownSafety:
    """The renderer must never let raw HTML through (HTMX/XSS safe)."""

    @pytest.mark.parametrize(
        "payload",
        [
            "<script>alert(1)</script>",
            '<img src=x onerror="alert(1)">',
            '<a href="javascript:alert(1)">x</a>',
        ],
    )
    def test_html_is_escaped(self, payload):
        html = render_markdown(payload)
        assert "<script>" not in html
        assert "<img" not in html
        assert "onerror" not in html.replace("&quot;", "") or "&lt;" in html
        # The payload text is still visible, but escaped
        assert "&lt;" in html

    def test_html_in_markdown_structure_is_escaped(self):
        html = render_markdown("- **bold** and <b>not bold</b>")
        assert "<b>not bold</b>" not in html
        assert "&lt;b&gt;not bold&lt;/b&gt;" in html
        assert "<strong>bold</strong>" in html

    def test_javascript_scheme_link_is_neutralized(self):
        html = render_markdown("[x](javascript:alert(1))")
        assert 'href="javascript:' not in html

    def test_quote_in_link_url_is_escaped(self):
        """A double quote in a link URL must not break out of the href attribute.

        Regression test for XSS: the renderer escapes text with
        quote=False, so a raw `"` inside a URL could previously terminate
        the href attribute and inject arbitrary event handlers.
        """
        html = render_markdown('[click](x"onmouseover="alert(document.cookie))')
        assert 'onmouseover="alert' not in html
        # The quote is entity-escaped inside the attribute value.
        assert (
            """ in html
        assert html.count('href="') == 1

    def test_quote_in_link_url_variants(self):
        for payload in [
            '[a](x"y)',
            '[a](x" onclick="alert(1))',
            '[a]("+autofocus+onfocus=alert(1))',
        ]:
            html = render_markdown(payload)
            assert html.count("<a ") == html.count('<a href="')
            assert "onclick=" not in html
            assert "onfocus=" not in html

    def test_normal_link_still_works_after_quote_escaping(self):
        html = render_markdown("see [docs](https://example.com/?a=1&b=2)")
        assert 'href="https://example.com/?a=1&b=2"' in html
        assert """
            not in html
        )


class TestMarkdownImages:
    """Image syntax (JRB-027): only app-hosted image URLs render as <img>.

    Uploaded screenshots live under the app's ``/images/<name>`` route. Any
    other URL (remote, ``data:``, traversal) must stay literal escaped text so
    a description cannot inject markup or pull remote image content.
    """

    def test_app_hosted_image_renders_as_img(self):
        html = render_markdown("![screenshot](/images/abc123.png)")
        assert html == '<p><img src="/images/abc123.png" alt="screenshot"></p>'

    def test_image_without_alt_text(self):
        html = render_markdown("![](/images/def456.webp)")
        assert html == '<p><img src="/images/def456.webp" alt=""></p>'

    def test_image_allowed_name_characters(self):
        html = render_markdown("![x](/images/A-b_c.9.jpg)")
        assert html == '<p><img src="/images/A-b_c.9.jpg" alt="x"></p>'

    def test_image_inline_with_surrounding_text(self):
        html = render_markdown("before ![shot](/images/x.gif) after")
        assert html == '<p>before <img src="/images/x.gif" alt="shot"> after</p>'

    def test_image_survives_bold_and_italic_processing(self):
        """The image is stashed like links, so inline markers inside alt/URL
        stay inert (no <strong>/<em> inside the emitted tag)."""
        html = render_markdown("![**alt** _more_](/images/x.png)")
        assert html == '<p><img src="/images/x.png" alt="**alt** _more_"></p>'

    def test_image_alt_quote_is_attribute_escaped(self):
        """The description text is escaped with quote=False upstream, so a raw
        `"` in the alt text must be entity-escaped for the alt attribute."""
        html = render_markdown('![a"b](/images/x.png)')
        assert html == '<p><img src="/images/x.png" alt="a&quot;b"></p>'

    @pytest.mark.parametrize(
        "markup",
        [
            "![x](https://evil.example.com/track.png)",
            "![x](http://evil.example.com/track.png)",
            "![x](//evil.example.com/track.png)",
            "![x](data:image/png;base64,AAAA)",
            "![x](javascript:alert(1))",
            "![x](../secrets.txt)",
            "![x](/images/..%2f..%2fjackrabbit.db)",
            "![x](/images/sub/dir.png)",
            '![x](/images/x"onerror="alert(1))',
        ],
    )
    def test_unsafe_image_urls_stay_literal_text(self, markup):
        """Non app-hosted image URLs must not become <img> tags or remote loads."""
        html = render_markdown(markup)
        assert "<img" not in html
        # The markup remains visible as literal text (the description is
        # escaped with quote=False, so a raw `"` stays raw in literal text).
        assert markup in html

    def test_unsafe_image_inside_paragraph_with_text(self):
        html = render_markdown("look ![x](https://evil.example.com/a.png) now")
        assert "<img" not in html
        assert "![x](https://evil.example.com/a.png)" in html

    def test_link_syntax_still_renders_after_image_support(self):
        html = render_markdown("see [docs](https://example.com)")
        assert '<a href="https://example.com"' in html

    def test_link_that_looks_like_image_stays_a_link(self):
        html = render_markdown("[not an image](/images/x.png)")
        assert "<img" not in html
        assert '<a href="/images/x.png"' in html
