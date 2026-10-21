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
})();
