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
    popover.classList.add("ms-open");
    sizePopover(popover);
    var trigger = document.querySelector(
      '[data-ms-trigger][data-ms-field="' +
        popover.getAttribute("data-ms-field") +
        '"]'
    );
    if (trigger) {
      trigger.setAttribute("aria-expanded", "true");
    }
  }

  // Keep a dropdown from growing past the controls below it (the "All"
  // checkbox + options + mode block could otherwise overlap the Labels panel
  // and the Filter/Submit row, making them unclickable). The panel scrolls
  // within the cap; Playwright's check()/click() scroll it to reveal any
  // option, and the Submit button stays outside the popover's box entirely.
  function sizePopover(popover) {
    var anchor = document.getElementById("backlog-submit-row");
    if (!anchor) return;
    var field = popover.closest("[data-ms-field]");
    if (!field) return;
    var fieldBottom = field.getBoundingClientRect().bottom;
    var anchorTop = anchor.getBoundingClientRect().top;
    var max = Math.max(120, Math.round(anchorTop - fieldBottom - 8));
    popover.style.maxHeight = max + "px";
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
        if (open) sizePopover(open);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMultiSelect);
  } else {
    initMultiSelect();
  }
  // Re-init after every htmx swap, in case the form is re-rendered.
  document.body.addEventListener("htmx:afterOnLoad", initMultiSelect);
})();
