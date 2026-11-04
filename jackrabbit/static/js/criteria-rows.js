/* Acceptance-criteria row editor (JRB-023, ADR-0025).
 *
 * Add/remove controls for the repeatable criteria rows in the grooming
 * surfaces (Groomed transition modal + ticket-detail edit form). On submit
 * the trimmed, non-empty row values replace the form's `criteria` parameter:
 * when the rows are unchanged from the server-rendered snapshot the
 * parameter is dropped entirely, so a plain field save neither replaces the
 * rows nor trips the criteria-locked guard for a ticket past Groomed.
 */
(function () {
    "use strict";

    var INPUT_CLASS = "w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm " +
        "focus:outline-none focus:ring-indigo-500 focus:border-indigo-500";
    var REMOVE_CLASS = "shrink-0 w-7 h-7 rounded-full border border-gray-300 " +
        "text-gray-500 hover:text-red-600 hover:border-red-400 leading-none";

    function originalCriteria(field) {
        try {
            return JSON.parse(field.getAttribute("data-original-criteria") || "[]");
        } catch (err) {
            return null;
        }
    }

    function currentValues(field) {
        var values = [];
        var inputs = field.querySelectorAll("input[name='criteria']");
        for (var i = 0; i < inputs.length; i++) {
            var value = inputs[i].value.trim();
            if (value.length > 0) {
                values.push(value);
            }
        }
        return values;
    }

    function makeRow(field) {
        var row = document.createElement("div");
        row.className = "flex items-center gap-2";
        row.setAttribute("data-criteria-row", "");
        var input = document.createElement("input");
        input.type = "text";
        input.setAttribute("name", "criteria");
        input.className = INPUT_CLASS;
        input.placeholder = "Describe one criterion...";
        var remove = document.createElement("button");
        remove.type = "button";
        remove.setAttribute("data-criteria-remove", "");
        remove.setAttribute("aria-label", "Remove criterion");
        remove.className = REMOVE_CLASS;
        remove.textContent = "\u00d7";
        row.appendChild(input);
        row.appendChild(remove);
        return row;
    }

    function initField(field) {
        if (field.getAttribute("data-criteria-ready") === "1") {
            return;
        }
        field.setAttribute("data-criteria-ready", "1");

        var rows = field.querySelector("[data-criteria-rows]");
        var add = field.querySelector("[data-criteria-add]");
        var form = field.closest("form");
        if (!rows || !form) {
            return;
        }

        if (add) {
            add.addEventListener("click", function () {
                rows.appendChild(makeRow(field));
                var inputs = rows.querySelectorAll("input[name='criteria']");
                inputs[inputs.length - 1].focus();
            });
        }

        rows.addEventListener("click", function (event) {
            var button = event.target.closest("[data-criteria-remove]");
            if (!button) {
                return;
            }
            var row = button.closest("[data-criteria-row]");
            if (row) {
                row.remove();
            }
        });

        form.addEventListener("htmx:configRequest", function (event) {
            var values = currentValues(field);
            var original = originalCriteria(field);
            if (original !== null && JSON.stringify(original) === JSON.stringify(values)) {
                // Unchanged from the server-rendered rows: submit nothing, so
                // the server leaves the existing rows untouched.
                delete event.detail.parameters.criteria;
            } else {
                event.detail.parameters.criteria = values;
            }
        });
    }

    var fields = document.querySelectorAll("[data-criteria-field]");
    for (var i = 0; i < fields.length; i++) {
        initField(fields[i]);
    }
})();
