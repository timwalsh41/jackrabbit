# ADR-0022: Vendor Frontend Assets Locally (No CDN at Page Load)

## Status
Accepted

## Context
`base.html` loaded htmx, the htmx `json-enc` extension, hyperscript, and Tailwind from
`unpkg.com`/`cdn.jsdelivr.net`. Two problems: Jackrabbit is a local-first single-user tool
(ADR-0001, ADR-0004) whose page loads should not depend on third-party availability, and the
Tailwind URL was already dead — `tailwindcss@3.4.1` ships no `dist/tailwind.min.css`, so the
request 404'd and **every page rendered unstyled** while all e2e tests stayed green, because
they only assert on DOM/text.

## Decision
Serve every asset from `/static`. Vendor `htmx.min.js` and `htmx-json-enc.js` under
`jackrabbit/static/vendor/`, and commit a Tailwind stylesheet purged from the templates at
`jackrabbit/static/css/tailwind.css`. The Tailwind source config (`frontend/`) is build-only
tooling; running the app needs no Node. hyperscript is dropped — no `_="…"` attribute is used
anywhere in the templates.

Rebuild with `make build-css`; `make css-check` (also a CI step) fails if the committed
stylesheet is stale.

## Consequences

### Positive
- Works offline and behind CSP/air-gapped networks; no third-party outage can blank the UI
- A missing stylesheet is now a *loud* failure: `tests/unit/test_static_assets.py` and
  `tests/e2e/test_assets_and_styling.py` assert no external URLs, resolvable local paths,
  non-trivial rule counts, and concrete computed styles
- Purged CSS is ~25 KB instead of a multi-megabyte CDN bundle

### Negative
- Vendored files are committed bytes that must be refreshed by hand on upgrade
- Tailwind utility classes introduced in a template require a `make build-css` before they
  render; CI's `css-check` step is the backstop

## Alternatives Considered
- **Keep the CDNs and pin the correct Tailwind URL**: rejected — leaves the app dependent on
  third-party availability, which contradicts the local-first premise.
- **Compile a full utility bundle by hand**: rejected — re-implementing Tailwind's purge step
  for no benefit.
- **Write our own CSS**: rejected — the templates already speak Tailwind utilities (652 of 733
  class attributes).
