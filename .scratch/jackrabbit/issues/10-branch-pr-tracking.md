# 10: Branch & PR Tracking

**What to build:** Auto-set `branch_name` on In Progress transition (format `{project}-{number}-{slug}`), `pr_url` on Ready for Review. Displayed on ticket detail.

**Blocked by:** 05

**Status:** ready-for-agent

- [ ] Slug generation: `title.lower().replace(' ', '-').replace('_', '-')`, strip non-alphanumeric/hyphen, truncate 50 chars
- [ ] On `Open → Groomed → In Progress` transition:
  - If `branch_name` empty, auto-generate `{prefix}-{number:03d}-{slug}` and set on ticket
  - User can override before confirming transition
- [ ] On `In Progress → Ready for Review` transition:
  - Require `pr_url` (valid HTTP(S) URL); set on ticket
- [ ] Ticket detail shows:
  - Branch name (monospace, copy button) — links to GitHub/GitLab if detectable pattern
  - PR URL (link, copy button)
- [ ] Web: Transition modals for In Progress / Ready for Review include pre-filled branch/PR fields (editable)
- [ ] Service: `generate_branch_name(ticket)` — uses current project prefix + number + slug
- [ ] Unit tests: slug generation edge cases (unicode, long titles, special chars), branch format, PR URL validation