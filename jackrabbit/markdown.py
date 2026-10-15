"""Minimal, dependency-free, HTML-escaping Markdown renderer.

Used to render ticket descriptions "HTMX safe": every character that could
form HTML is escaped *first*, so user content can never inject markup; only
the structural tags this module itself emits are trusted HTML.

Supported syntax (a pragmatic subset for ticket text):
- Headings: ``#`` .. ``######`` at line start
- Bold: ``**text``
- Italic: ``*text
- Inline code: `` `text` ``
- Fenced code blocks: triple-backtick fences
- Links: ``[text](url)`` (``javascript:`` URLs are neutralized)
- Unordered lists: lines starting with ``- `` or ``* ``
- Ordered lists: lines starting with ``1. `` (digits + dot)
- Paragraphs separated by blank lines; single newlines become ``<br>``
"""

import html
import re

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+)\*(?!\*)")
_CODE_RE = re.compile(r"`([^`\n]+)`")
_LINK_RE = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+)\)")
_LIST_ITEM_RE = re.compile(r"^(?:[-*]|\d+\.)\s+(.*)$")

_DANGEROUS_URL_SCHEMES = ("javascript:", "vbscript:", "data:")


def _render_inline(text: str) -> str:
    """Render inline markdown (bold/italic/code/links) on escaped text."""
    # Inline code first so other markers inside code spans stay literal.
    placeholders: list[str] = []

    def _stash(html_span: str) -> str:
        placeholders.append(html_span)
        return f"\x00{len(placeholders) - 1}\x00"

    text = _CODE_RE.sub(lambda m: _stash(f"<code>{m.group(1)}</code>"), text)
    text = _LINK_RE.sub(lambda m: _stash_url(m.group(1), m.group(2), placeholders), text)
    text = _BOLD_RE.sub(r"<strong>\1</strong>", text)
    text = _ITALIC_RE.sub(r"<em>\1</em>", text)
    text = _stash_code_blocks_back(text, placeholders)
    return text


def _stash_url(label: str, url: str, placeholders: list[str]) -> str:
    lowered = url.lower()
    if any(lowered.startswith(scheme) for scheme in _DANGEROUS_URL_SCHEMES):
        # Neutralize the href but keep the label visible.
        return f'<a href="#" rel="noopener noreferrer">{label}</a>'
    return f'<a href="{url}" target="_blank" rel="noopener noreferrer">{label}</a>'


def _stash_code_blocks_back(text: str, placeholders: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], text)


def _render_blocks(escaped: str) -> str:
    lines = escaped.split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    in_code_block = False
    code_lines: list[str] = []
    list_items: list[str] | None = None
    list_tag = "ul"

    def flush_paragraph() -> None:
        if paragraph:
            out.append("<p>" + "<br>".join(paragraph) + "</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_items, list_tag
        if list_items:
            out.append(f"<{list_tag}>" + "".join(list_items) + f"</{list_tag}>")
            list_items = None

    for line in lines:
        if in_code_block:
            if line.strip().startswith("```"):
                out.append("<pre><code>" + "\n".join(code_lines) + "</code></pre>")
                code_lines = []
                in_code_block = False
            else:
                code_lines.append(line)
            continue

        if line.strip().startswith("```"):
            flush_paragraph()
            flush_list()
            in_code_block = True
            continue

        stripped = line.strip()

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            out.append(f"<h{level}>{heading.group(2)}</h{level}>")
            continue

        item = _LIST_ITEM_RE.match(stripped)
        if item:
            flush_paragraph()
            ordered = stripped[:1].isdigit()
            if list_items is None or (list_tag == "ul") != (not ordered):
                flush_list()
                list_tag = "ol" if ordered else "ul"
                list_items = []
            list_items.append(f"<li>{_render_inline(item.group(1))}</li>")
            continue

        flush_list()
        if stripped == "":
            flush_paragraph()
        else:
            paragraph.append(_render_inline(stripped))

    # An unterminated fence still renders its content.
    if in_code_block and code_lines:
        out.append("<pre><code>" + "\n".join(code_lines) + "</code></pre>")
    flush_paragraph()
    flush_list()
    return "".join(out)


def render_markdown(text: str) -> str:
    """Render markdown text to trusted HTML, escaping all raw HTML first."""
    if not text:
        return ""
    escaped = html.escape(text, quote=False)
    return _render_blocks(escaped)
