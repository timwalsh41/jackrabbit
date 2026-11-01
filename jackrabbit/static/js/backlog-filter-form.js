/* Backlog filter form.
 *
 * Two concerns:
 *
 * 1. Keep the form in step with the table. The sortable column headers and the
 *    pagination links include the filter form (#backlog-filter-form) instead of
 *    restating its values, so the form is the single source of truth for the
 *    active filters. Its hidden sort/order fields therefore have to follow the
 *    sort the table is actually showing: after a header is clicked the server
 *    sorts by that column, and the next request (a page click, or a filter
 *    submit) has to ask for the same sort. htmx reports the parameters of
 *    every request it makes, so the sort and the order of the last request
 *    are copied into the form's hidden fields.
 *
 * 2. Drive the multi-select dropdown component. Each filter
 *    (Project/Type/Status/Priority/Sprint) is a button (data-ms-trigger) that
 *    toggles a popover (data-ms-popover) of checkboxes (data-ms-option). The
 *    visible checkboxes are the form controls that HTMX serializes via
 *    hx-include="#backlog-filter-form", so there is no <select> in the markup.
 *    The "All" checkbox (data-ms-select-all) checks every option in its
 *    popover; the Project/Type/Status include/exclude radios live inside their
 *    popover too. The trigger label tracks the count ("All" / "N selected").
 */
(function () {
  "use strict";

  var SORT_FIELDS = ["sort", "order"];
  var MIN_POPOVER_WIDTH = 280;
  var MAX_POPOVER_WIDTH = 420;
  var VIEWPORT_PADDING = 12;

  /* ---- filter persistence (sessionStorage, per tab) ----
   *
   * The backlog is entered with no query params when the user returns to it
   * from another view (the nav link in base.html is a plain /backlog link),
   * so the active filters would be lost. They are stashed in sessionStorage:
   * per-tab and cleared when the tab closes - literal "for a session"
   * semantics. One capture point covers filter submits, sort clicks and
   * pagination (all use hx-push-url=true and include the filter form, so
   * every one of them pushes a /backlog URL whose query IS the filter state);
   * htmx:historyRestore covers Browser Back/Forward between htmx-pushed
   * filter URLs - the restore path is the state being navigated to, so it
   * rewrites the stash too (otherwise the newer query would win over the
   * older one the user just went back to).
   *
   * Full-page loads are the other capture point: a load of a /backlog URL
   * that already carries a query (project-scoped links, shared URLs, browser
   * back/forward across full pages) is a deliberate state, so that query is
   * stashed as the newest one. A parameter-less /backlog load stashes
   * nothing - it is exactly the nav-link return whose stash we want to
   * restore from.
   *
   * One global stash per tab, not per project: the last seen backlog query
   * wins. URLs that already carry params are honored as-is AND update the
   * stash.
   */
  var FILTER_STASH_KEY = "backlog-filter-query";
  var HIDDEN_FIELDS = ["sort", "order", "page", "page_size"];
  // Params the restore must NOT apply: the pagination controls and the
  // sort-header toggles in thead were rendered by the server for this
  // param-less load (page 1, default page size), and the restore's
  // re-submit swaps only #tickets-table-body. Applying a stashed page=2
  // would show page-two rows under controls that omit Previous and still
  // read "Page 1 of N" (and Next would re-request page 2), so page and
  // page_size reset to the rendered defaults - "page reset to 1" per the
  // ticket's test plan, while filters, sort and order are preserved.
  var PAGE_PARAMS = ["page", "page_size"];
  var CHECKBOX_FIELDS = [
    "project_ids",
    "types",
    "statuses",
    "priorities",
    "sprint_ids",
    "label_ids",
  ];
  var MODE_RADIOS = ["project_filter_mode", "type_filter_mode", "status_filter_mode"];
  var VALUE_FIELDS = ["q", "created_after", "created_before", "label_match"];
  // Backward-compat single-value params the server still accepts but the form
  // has no field for: the URL pre-checks the matching multi-select option
  // (server-side, via effective_*_ids), so a stashed URL using one must map
  // to the same checkbox when restored. Values are identical.
  var SINGLE_TO_MULTI = {
    project_id: "project_ids",
    status: "statuses",
    type: "types",
    priority: "priorities",
    sprint_id: "sprint_ids",
  };

  function stashQuery(query) {
    try {
      sessionStorage.setItem(FILTER_STASH_KEY, query);
    } catch (err) {
      /* Storage unavailable (private mode, quota): persistence degrades to
       * the old behaviour of losing filters on navigation. */
    }
  }

  function readStash() {
    try {
      return sessionStorage.getItem(FILTER_STASH_KEY);
    } catch (err) {
      return null;
    }
  }

  // Capture: every pushed URL that is a /backlog URL rewrites the stash with
  // its query string (empty when the pushed URL has none, which itself is a
  // valid state - e.g. right after Clear filters).
  function onPushedIntoHistory(event) {
    var path = (event.detail && event.detail.path) || "";
    var querySplit = path.indexOf("?");
    if (querySplit === -1) {
      if (path !== "/backlog") {
        return;
      }
      stashQuery("");
      return;
    }
    if (path.slice(0, querySplit) !== "/backlog") {
      return;
    }
    stashQuery(path.slice(querySplit + 1));
  }

  // Capture the other direction: a full-page load of a /backlog URL that
  // already carries a query is the newest state (project-scoped link, shared
  // URL, browser back/forward). Stash it so leaving through the nav link and
  // coming back restores THIS query, not an older one. A parameter-less
  // backlog load is skipped - it must not wipe the stash it is about to
  // restore from.
  function stashExplicitUrl() {
    if (window.location.pathname !== "/backlog") {
      return;
    }
    var query = window.location.search.replace(/^\?/, "");
    if (query === "") {
      return;
    }
    stashQuery(query);
  }

  // Populate #backlog-filter-form from the stashed query params. Checkboxes
  // are first all unchecked, then the requested values are checked, so the
  // form ends up exactly matching the stored selection.
  function applyParamsToForm(form, params) {
    HIDDEN_FIELDS.forEach(function (name) {
      var field = form.querySelector('input[type="hidden"][name="' + name + '"]');
      var value = params.get(name);
      if (field && value !== null) {
        field.value = value;
      }
    });
    CHECKBOX_FIELDS.forEach(function (name) {
      var wanted = params.getAll(name);
      // A single-value compat param in the URL pre-checks its multi-select
      // option too (that is how the server renders such a URL), so the form
      // can express the stashed query on the restore re-submit.
      Object.keys(SINGLE_TO_MULTI).forEach(function (single) {
        if (SINGLE_TO_MULTI[single] !== name) {
          return;
        }
        var value = params.get(single);
        if (value !== null && value !== "" && wanted.indexOf(value) === -1) {
          wanted = wanted.concat([value]);
        }
      });
      var boxes = form.querySelectorAll('input[type="checkbox"][name="' + name + '"]');
      for (var i = 0; i < boxes.length; i++) {
        boxes[i].checked = wanted.indexOf(boxes[i].value) !== -1;
      }
    });
    MODE_RADIOS.forEach(function (name) {
      var wanted = params.get(name) || "include";
      var radios = form.querySelectorAll('input[type="radio"][name="' + name + '"]');
      for (var i = 0; i < radios.length; i++) {
        radios[i].checked = radios[i].value === wanted;
      }
    });
    VALUE_FIELDS.forEach(function (name) {
      var field = form.querySelector('[name="' + name + '"]');
      var value = params.get(name);
      if (field && value !== null) {
        field.value = value;
      }
    });
    var panel = form.querySelector("#labels-filter-panel");
    if (panel && params.getAll("label_ids").length > 0) {
      panel.open = true;
    }
  }

  // Restore: on a parameter-less backlog page load with a stored query, put
  // the query back into the form and re-trigger its hx-get (hx-push-url
  // rewrites the URL to the filtered query, so the address bar catches up).
  // URLs that already carry params are skipped - they say what they mean.
  function restoreBacklogFilters() {
    var form = document.getElementById("backlog-filter-form");
    if (!form) {
      return;
    }
    if (window.location.pathname !== "/backlog" || window.location.search !== "") {
      return;
    }
    var stored = readStash();
    if (!stored) {
      return;
    }
    var params;
    try {
      params = new URLSearchParams(stored);
    } catch (err) {
      return;
    }
    if (!Array.from(params.keys()).length) {
      return;
    }
    PAGE_PARAMS.forEach(function (name) {
      params.delete(name);
    });
    // The thead sort headers were rendered for the default sort. Their
    // hx-vals override the form's hidden sort/order fields, so a stale
    // toggle would re-send the wrong order when the header of the restored
    // sort is clicked; recompute them (and the arrows) from the stash.
    syncSortHeaders(params);
    applyParamsToForm(form, params);
    if (window.htmx) {
      window.htmx.trigger(form, "submit");
    }
  }

  // Sort arrows are plain text at the end of the header: strip any previous
  // arrow, then mark the active column (null leaves the header unmarked).
  var SORT_ARROWS = { asc: "\u2191", desc: "\u2193" };

  function setSortHeaderArrow(th, order) {
    var arrow = order ? SORT_ARROWS[order] : null;
    var nodes = th.childNodes;
    for (var i = nodes.length - 1; i >= 0; i--) {
      if (nodes[i].nodeType === 3) {
        nodes[i].textContent = nodes[i].textContent.replace(/[\u2191\u2193]/g, "");
      }
    }
    if (arrow) {
      th.appendChild(document.createTextNode(" " + arrow));
    }
  }

  // Recompute the sort-header toggles to match a restored sort/order, using
  // the same rule the template renders: the active column in desc flips to
  // asc, every other column sorts desc first. hx-vals win over included form
  // values in htmx, so without this a click on the header of the restored
  // sort would re-send the order the default render baked in, not toggle.
  function syncSortHeaders(params) {
    var activeSort = params.get("sort");
    var activeOrder = params.get("order") || "desc";
    if (!activeSort) {
      return;
    }
    var headers = document.querySelectorAll("th[hx-vals]");
    for (var i = 0; i < headers.length; i++) {
      var th = headers[i];
      var vals;
      try {
        vals = JSON.parse((th.getAttribute("hx-vals") || "").replace(/^js:/, ""));
      } catch (err) {
        continue;
      }
      if (!vals || !vals.sort) {
        continue;
      }
      var isActive = vals.sort === activeSort;
      vals.order = isActive && activeOrder === "desc" ? "asc" : "desc";
      th.setAttribute("hx-vals", "js:" + JSON.stringify(vals));
      setSortHeaderArrow(th, isActive ? activeOrder : null);
    }
  }

  // Clear filters: wipe the stash before the plain link navigates, so the
  // param-less backlog load that follows stays unfiltered.
  function onClearFiltersClick(event) {
    if (!event.target.closest("[data-clear-filters]")) {
      return;
    }
    stashKeyRemoval();
  }

  function stashKeyRemoval() {
    try {
      sessionStorage.removeItem(FILTER_STASH_KEY);
    } catch (err) {
      /* Storage unavailable: nothing stashed, nothing to wipe. */
    }
  }

  function syncForm(event) {
    var detail = event.detail || {};
    var parameters = detail.parameters || {};
    var form = document.getElementById("backlog-filter-form");
    if (!form) {
      return;
    }
    SORT_FIELDS.forEach(function (name) {
      var value = parameters[name];
      if (value === undefined || value === null || value === "") {
        return;
      }
      var field = form.querySelector('input[name="' + name + '"]');
      if (field) {
        field.value = value;
      }
    });
  }

  document.addEventListener("htmx:configRequest", syncForm);
  // Browser Back/Forward between htmx-pushed filter URLs fires
  // htmx:historyRestore, not htmx:pushedIntoHistory - the restored path is
  // the state being navigated to, so it rewrites the stash as well.
  document.body.addEventListener("htmx:pushedIntoHistory", onPushedIntoHistory);
  document.body.addEventListener("htmx:historyRestore", onPushedIntoHistory);
  document.addEventListener("click", onClearFiltersClick);

  /* ---- multi-select dropdown component ---- */

  // The popover container is positioned relative to the trigger's .ms-field
  // wrapper via CSS; the field name ties them together.
  function findPopover(trigger) {
    var field = trigger.getAttribute("data-ms-field");
    return document.querySelector(
      '[data-ms-popover][data-ms-field="' + field + '"]'
    );
  }

  function optionsIn(popover) {
    return popover.querySelectorAll("[data-ms-option]");
  }

  function closePopover(popover) {
    if (!popover) return;
    popover.classList.remove("ms-open");
    popover.hidden = true;
    popover.setAttribute("aria-hidden", "true");
    var trigger = document.querySelector(
      '[data-ms-trigger][data-ms-field="' +
        popover.getAttribute("data-ms-field") +
        '"]'
    );
    if (trigger) {
      trigger.setAttribute("aria-expanded", "false");
    }
  }

  function openPopover(popover) {
    // Only one popover open at a time.
    var open = document.querySelector(".ms-popover.ms-open");
    if (open && open !== popover) {
      closePopover(open);
    }
    popover.hidden = false;
    popover.setAttribute("aria-hidden", "false");
    popover.classList.add("ms-open");
    sizePopoverWidth(popover);
    var trigger = document.querySelector(
      '[data-ms-trigger][data-ms-field="' +
        popover.getAttribute("data-ms-field") +
        '"]'
    );
    if (trigger) {
      trigger.setAttribute("aria-expanded", "true");
    }
  }

  // The popover starts at a useful minimum width, then grows to the widest
  // unwrapped option text. It is capped so a long project or sprint name does
  // not consume the whole page, and constrained by the viewport on narrow
  // screens. Once the final width is applied, normal wrapping remains a safe
  // fallback for text longer than the cap.
  function sizePopoverWidth(popover) {
    var field = popover.closest(".ms-field");
    if (!field) return;

    var viewportWidth = Math.max(0, window.innerWidth - VIEWPORT_PADDING * 2);
    var trigger = field.querySelector("[data-ms-trigger]");
    var triggerWidth = trigger ? trigger.getBoundingClientRect().width : 0;
    var maxWidth = Math.min(MAX_POPOVER_WIDTH, viewportWidth);

    // Measure the natural width before the final cap is applied. max-content
    // prevents wrapped labels from making the measurement artificially small.
    popover.style.width = "max-content";
    popover.style.maxWidth = "none";
    var naturalWidth = popover.getBoundingClientRect().width;
    var width = Math.max(MIN_POPOVER_WIDTH, triggerWidth, naturalWidth);
    width = Math.min(width, maxWidth);

    popover.style.width = Math.floor(width) + "px";
    popover.style.maxWidth = maxWidth + "px";
  }

  function countSelected(popover) {
    var n = 0;
    var opts = optionsIn(popover);
    for (var i = 0; i < opts.length; i++) {
      if (opts[i].checked) n += 1;
    }
    return n;
  }

  function refreshTrigger(trigger, popover) {
    var label = trigger.querySelector(".ms-trigger-text");
    if (!label) return;
    var total = optionsIn(popover).length;
    var n = countSelected(popover);
    label.textContent = n === 0 ? "All" : n + " selected";
  }

  function refreshSelectAll(popover) {
    var cb = popover.querySelector("[data-ms-select-all]");
    if (!cb) return;
    var total = optionsIn(popover).length;
    var n = countSelected(popover);
    cb.indeterminate = n > 0 && n < total;
    cb.checked = n === total;
  }

  function refreshField(trigger) {
    var popover = findPopover(trigger);
    if (!popover) return;
    refreshTrigger(trigger, popover);
    refreshSelectAll(popover);
  }

  function onTriggerClick(event) {
    var trigger = event.currentTarget;
    var popover = findPopover(trigger);
    if (!popover) return;
    if (popover.classList.contains("ms-open")) {
      closePopover(popover);
    } else {
      openPopover(popover);
    }
  }

  function onOptionChange(event) {
    var opt = event.target;
    if (!opt.hasAttribute("data-ms-option")) return;
    // Keep this change from closing the popover (clicking an option is a
    // multi-select action, not a "click away"). The document click handler
    // lets it through; here we just re-sync the label + select-all state.
    var popover = opt.closest("[data-ms-popover]");
    if (!popover) return;
    var trigger = document.querySelector(
      '[data-ms-trigger][data-ms-field="' + popover.getAttribute("data-ms-field") + '"]'
    );
    if (trigger) refreshField(trigger);
  }

  function onSelectAllChange(event) {
    var cb = event.target;
    if (!cb.hasAttribute("data-ms-select-all")) return;
    var popover = cb.closest("[data-ms-popover]");
    if (!popover) return;
    var check = cb.checked;
    var opts = optionsIn(popover);
    for (var i = 0; i < opts.length; i++) {
      opts[i].checked = check;
      // Dispatch change so any listener (and htmx, if it tracked inputs) sees
      // the update; also updates the trigger label via onOptionChange.
      opts[i].dispatchEvent(new window.Event("change", { bubbles: true }));
    }
    refreshSelectAll(popover);
    var trigger = document.querySelector(
      '[data-ms-trigger][data-ms-field="' + popover.getAttribute("data-ms-field") + '"]'
    );
    if (trigger) refreshTrigger(trigger, popover);
  }

  // Click outside any open popover closes it. Clicks that originate inside an
  // open popover (checkbox / radio / select-all) are allowed to bubble up
  // without closing, so multi-select stays usable.
  function onDocumentClick(event) {
    var open = document.querySelector(".ms-popover.ms-open");
    if (!open) return;
    var target = event.target;
    if (target.closest("[data-ms-trigger]") || open.contains(target)) {
      return;
    }
    closePopover(open);
  }

  function onDocumentKeydown(event) {
    if (event.key === "Escape") {
      closePopover(document.querySelector(".ms-popover.ms-open"));
    }
  }

  function initMultiSelect() {
    var bound = document.querySelectorAll("[data-ms-trigger]");
    for (var i = 0; i < bound.length; i++) {
      var trigger = bound[i];
      if (trigger.hasAttribute("data-ms-bound")) continue;
      trigger.setAttribute("data-ms-bound", "");

      var popover = findPopover(trigger);
      if (!popover) continue;

      // The hidden attribute is the authoritative closed state. CSS adds the
      // presentation and transition, but the dropdown stays closed even if
      // the enhancement stylesheet is unavailable.
      popover.hidden = true;
      popover.setAttribute("aria-hidden", "true");
      trigger.setAttribute("aria-expanded", "false");

      trigger.addEventListener("click", onTriggerClick);

      // Wire every option checkbox in this field's popover.
      var opts = optionsIn(popover);
      for (var j = 0; j < opts.length; j++) {
        opts[j].addEventListener("change", onOptionChange);
      }
      var selectAll = popover.querySelector("[data-ms-select-all]");
      if (selectAll) selectAll.addEventListener("change", onSelectAllChange);

      refreshField(trigger);
    }

    if (!document.body.hasAttribute("data-ms-doc-bound")) {
      document.body.setAttribute("data-ms-doc-bound", "");
      document.addEventListener("click", onDocumentClick);
      document.addEventListener("keydown", onDocumentKeydown);
      window.addEventListener("resize", function () {
        var open = document.querySelector(".ms-popover.ms-open");
        if (open) sizePopoverWidth(open);
      });
    }
  }

  function init() {
    initMultiSelect();
    // htmx processes the body on its own (earlier-registered) DOMContentLoaded
    // handler, so the form is already wired when the restore re-triggers it.
    stashExplicitUrl();
    restoreBacklogFilters();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
  // Re-init after every htmx swap, in case the form is re-rendered.
  document.body.addEventListener("htmx:afterOnLoad", initMultiSelect);
})();
