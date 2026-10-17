/**
 * Tailwind source config for the Jackrabbit SSR templates.
 *
 * The generated stylesheet is committed at
 * `jackrabbit/static/css/tailwind.css` so the app serves every asset locally
 * (no CDN at page-load time). Rebuild with `make build-css`.
 *
 * The `content` scan is a plain text search, so class names that appear only
 * inside JS string literals (`classList.add('bg-green-100')`) or in Jinja
 * `{% set %}` variables (`plan.html` status badges) are still picked up.
 */
module.exports = {
  content: [
    "../jackrabbit/templates/**/*.html",
    "../jackrabbit/static/js/**/*.js",
    "../jackrabbit/**/*.py",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
};
