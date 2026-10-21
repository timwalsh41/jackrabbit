/* Chip input for a ticket's labels field.
 *
 * Typed text is committed as a chip on Enter; every chip carries the label
 * name in a hidden `labels` input (comma-separated), so the form submits the
 * ticket's label names. The chip colour is derived from the label name the
 * same way the server derives it (FNV-1a over the lower-cased name onto the
 * shared palette), so a label looks the same in the form as on the ticket
 * page.
 */
(function () {
    "use strict";

    var MAX_LENGTH = 50;
    var NAME_PATTERN = /^[A-Za-z0-9 _:-]+$/;
    var PALETTE = [
        "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
        "#0ea5e9", "#ec4899", "#14b8a6", "#f97316", "#64748b"
    ];

    function fnv1a(text) {
        var hash = 0x811c9dc5;
        var bytes = new TextEncoder().encode(text);
        for (var i = 0; i < bytes.length; i++) {
            hash ^= bytes[i];
            hash = Math.imul(hash, 0x01000193) >>> 0;
        }
        return hash >>> 0;
    }

    function colorFor(name) {
        return PALETTE[fnv1a(name.trim().toLowerCase()) % PALETTE.length];
    }

    function names(field) {
        var values = field.querySelector("[data-label-values]");
        if (!values) {
            return [];
        }
        return values.value.split(",").map(function (name) {
            return name.trim();
        }).filter(function (name) {
            return name.length > 0;
        });
    }

    function initField(field) {
        if (field.getAttribute("data-labels-ready") === "1") {
            return;
        }
        field.setAttribute("data-labels-ready", "1");

        var input = field.querySelector("[data-label-input]");
        var chips = field.querySelector("[data-label-chips]");
        var values = field.querySelector("[data-label-values]");
        var error = field.querySelector("[data-label-error]");
        if (!input || !chips || !values) {
            return;
        }

        function showError(message) {
            if (!error) {
                return;
            }
            error.textContent = message;
            error.classList.remove("hidden");
        }

        function clearError() {
            if (!error) {
                return;
            }
            error.textContent = "";
            error.classList.add("hidden");
        }

        function syncValues() {
            values.value = names(field).join(",");
        }

        function removeChip(name) {
            var current = names(field).filter(function (existing) {
                return existing.toLowerCase() !== name.toLowerCase();
            });
            values.value = current.join(",");
            render(current);
        }

        function render(list) {
            chips.innerHTML = "";
            list.forEach(function (name) {
                var chip = document.createElement("span");
                chip.className = "label-chip inline-flex items-center gap-1 px-2.5 py-0.5 " +
                    "rounded-full text-xs font-medium text-white";
                chip.setAttribute("data-label-name", name);
                chip.style.backgroundColor = colorFor(name);

                var text = document.createElement("span");
                text.className = "label-chip-name";
                text.textContent = name;
                chip.appendChild(text);

                var remove = document.createElement("button");
                remove.type = "button";
                remove.className = "label-chip-remove opacity-70 hover:opacity-100";
                remove.setAttribute("data-label-remove", "1");
                remove.setAttribute("aria-label", "Remove label " + name);
                remove.title = "Remove label";
                remove.textContent = "×";
                remove.addEventListener("click", function () {
                    removeChip(name);
                });
                chip.appendChild(remove);

                chips.appendChild(chip);
            });
        }

        function addChip(rawName) {
            var name = (rawName || "").trim();
            clearError();
            if (!name) {
                return;
            }
            if (name.length > MAX_LENGTH) {
                showError("A label name may be at most " + MAX_LENGTH + " characters.");
                return;
            }
            if (!NAME_PATTERN.test(name)) {
                showError("A label name may only contain letters, digits, spaces, " +
                    "hyphens, underscores and colons.");
                return;
            }
            var current = names(field);
            var exists = current.some(function (existing) {
                return existing.toLowerCase() === name.toLowerCase();
            });
            if (exists) {
                showError("That label is already on this ticket.");
                return;
            }
            current.push(name);
            values.value = current.join(",");
            render(current);
        }

        // Existing labels (server-rendered) become the source of truth.
        render(names(field));

        input.addEventListener("keydown", function (event) {
            if (event.key !== "Enter") {
                return;
            }
            event.preventDefault();
            addChip(input.value);
            input.value = "";
        });

        input.addEventListener("blur", function () {
            if (input.value.trim()) {
                addChip(input.value);
                input.value = "";
            }
        });
    }

    function initAll(root) {
        var scope = root || document;
        if (scope.matches && scope.matches("[data-labels-field]")) {
            initField(scope);
        }
        var fields = scope.querySelectorAll("[data-labels-field]");
        Array.prototype.forEach.call(fields, initField);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initAll(document);
        });
    } else {
        initAll(document);
    }

    document.addEventListener("htmx:afterSwap", function (event) {
        initAll(event.target || document);
    });
})();
