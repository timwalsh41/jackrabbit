/* Clipboard image paste for the ticket description editors (JRB-027).
 *
 * A document-level paste listener covers all three ticket-description
 * textareas (new-ticket form, full-page edit form, backlog row-edit modal),
 * which are marked with data-description-editor — delegation means no init
 * wiring is needed for htmx-swapped modal content. An image in the clipboard
 * is uploaded to POST /api/v1/images (separate multipart fetch, never the
 * ticket form) and inserted as a markdown reference at the caret. Ordinary
 * text paste passes through untouched. Rejections (unsupported type, too
 * large) surface the server's detail message in the hidden red banner
 * ([data-image-error]) inside the same form.
 */
(function () {
    "use strict";

    // Mirrors jackrabbit.image_storage.MAX_IMAGE_BYTES.
    var MAX_BYTES = 10 * 1024 * 1024;

    function imageFiles(clipboardData) {
        var files = [];
        if (!clipboardData || !clipboardData.files) {
            return files;
        }
        for (var i = 0; i < clipboardData.files.length; i++) {
            var file = clipboardData.files[i];
            if (file && file.type && file.type.indexOf("image/") === 0) {
                files.push(file);
            }
        }
        return files;
    }

    function errorBanner(textarea) {
        var form = textarea.closest ? textarea.closest("form") : null;
        return form ? form.querySelector("[data-image-error]") : null;
    }

    function showError(textarea, message) {
        var banner = errorBanner(textarea);
        if (!banner) {
            return;
        }
        banner.textContent = message;
        banner.classList.remove("hidden");
    }

    function clearError(textarea) {
        var banner = errorBanner(textarea);
        if (!banner) {
            return;
        }
        banner.textContent = "";
        banner.classList.add("hidden");
    }

    function insertAtCaret(textarea, markdown) {
        if (typeof textarea.setRangeText === "function") {
            textarea.setRangeText(
                markdown,
                textarea.selectionStart || 0,
                textarea.selectionEnd || 0,
                "end"
            );
        } else {
            textarea.value += markdown;
        }
        // Keep htmx/json-enc and any other listeners in sync with the change.
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function uploadAndInsert(textarea, file) {
        var body = new FormData();
        body.append("file", file, file.name || "paste.png");
        fetch("/api/v1/images", {
            method: "POST",
            body: body,
            headers: { Accept: "application/json" }
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, status: response.status, data: data };
                });
            })
            .then(function (result) {
                if (!result.ok) {
                    var message =
                        result.data && typeof result.data.detail === "string"
                            ? result.data.detail
                            : "Image upload failed (" + result.status + ").";
                    showError(textarea, message);
                    return;
                }
                clearError(textarea);
                insertAtCaret(textarea, "![image](" + result.data.url + ")");
            })
            .catch(function () {
                showError(textarea, "Image upload failed. Please try again.");
            });
    }

    document.addEventListener("paste", function (event) {
        var target = event.target;
        if (!target || !target.matches || !target.matches("textarea[data-description-editor]")) {
            return;
        }
        var files = imageFiles(event.clipboardData);
        if (files.length === 0) {
            // Ordinary text paste: default browser behaviour.
            return;
        }
        event.preventDefault();
        clearError(target);
        files.forEach(function (file) {
            if (file.size > MAX_BYTES) {
                showError(target, "Image is too large. The maximum size is 10 MiB.");
                return;
            }
            uploadAndInsert(target, file);
        });
    });
})();
