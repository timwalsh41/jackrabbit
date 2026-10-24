/* Backlog filter form: keep the form in step with the table.
 *
 * The sortable column headers and the pagination links include the filter
 * form instead of restating its values, so the form is the single source of
 * truth for the active filters. Its hidden sort/order fields therefore have
 * to follow the sort the table is actually showing: after a header is clicked
 * the server sorts by that column, and the next request (a page click, or a
 * filter submit) has to ask for the same sort.
 *
 * htmx reports the parameters of every request it makes, so the sort and the
 * order of the last request are copied into the form's hidden fields.
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

  // "All" buttons on the backlog multi-selects: select every option in the
  // target <select multiple> so the user can quickly pick the whole list for
  // that field before clicking Filter. The target is the select's id, matched
  // by the button's data-target attribute.
  function selectAllIn(event) {
    var btn = event.currentTarget;
    var target = document.getElementById(btn.getAttribute("data-target"));
    if (!target || !target.options) {
      return;
    }
    for (var i = 0; i < target.options.length; i++) {
      target.options[i].selected = true;
    }
  }

  function bindAllButtons() {
    document.querySelectorAll(".all-btn[data-target]").forEach(function (btn) {
      // htmx may swap the table body in place; re-binding is idempotent.
      btn.removeEventListener("click", selectAllIn);
      btn.addEventListener("click", selectAllIn);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAllButtons);
  } else {
    bindAllButtons();
  }
  // Re-bind after every htmx swap, in case the form is re-rendered.
  document.body.addEventListener("htmx:afterOnLoad", bindAllButtons);
})();
