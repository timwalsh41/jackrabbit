/* Clipboard image paste for the ticket description editors (JRB-027).
 *
 * A document-level paste listener covers all three ticket-description
 * textareas (new-ticket form, full-page edit form, backlog row-edit modal),
 * which are marked with data-description-editor — delegation means no init
 * wiring is needed for htmx-swapped modal content. An image in the clipboard
 * is uploaded to POST /api/v1/images (separate multipart fetch, never the
 * ticket form) and inserted as a markdown reference at the caret position
 * captured when the paste happened (the user may type or move the caret while
 * the upload is in flight). Per-textarea work is serialized: images from one
 * paste keep their paste order, and a second paste made while the first is
 * still uploading inserts after it — its paste-time position is shifted by
 * every markdown inserted since it was captured, in queue order, so
 * concurrent pastes never land inside an earlier reference. Ordinary
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

    function insertAtCaret(textarea, markdown, start, end) {
        if (typeof textarea.setRangeText === "function") {
            textarea.setRangeText(markdown, start, end, "end");
        } else {
            textarea.value += markdown;
        }
        // Keep htmx/json-enc and any other listeners in sync with the change.
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
    }

    // Per textarea (WeakMap):
    // - insertQueues: one FIFO chain; uploads and insertions run in order, so
    //   images from one paste insert in paste order even when the uploads
    //   complete out of sequence, and a paste made while an earlier one is
    //   still in flight lands after it instead of racing it.
    // - insertedLengths: total markdown length inserted so far. Each paste
    //   captures this total as its `base`; when its turn comes it inserts at
    //   its captured offsets plus everything inserted since — including
    //   insertions queued by earlier pastes — so concurrent pastes keep their
    //   paste-time positions relative to the final text.
    var insertQueues = new WeakMap();
    var insertedLengths = new WeakMap();

    function uploadAndInsert(textarea, file, start, end, base) {
        var body = new FormData();
        body.append("file", file, file.name || "paste.png");
        var chain = insertQueues.get(textarea) || Promise.resolve();
        var task = chain
            .then(function () {
                return fetch("/api/v1/images", {
                    method: "POST",
                    body: body,
                    headers: { Accept: "application/json" }
                }).then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, status: response.status, data: data };
                    });
                });
            })
            .then(function (result) {
                if (!result.ok) {
                    var message =
                        result.data && typeof result.data.detail === "string"
                            ? result.data.detail
                            : "Image upload failed (" + result.status + ").";
                    showError(textarea, message);
                    return null;
                }
                clearError(textarea);
                return "![image](" + result.data.url + ")";
            })
            .catch(function () {
                showError(textarea, "Image upload failed. Please try again.");
                return null;
            })
            .then(function (markdown) {
                if (markdown === null) {
                    return;
                }
                // The paste-time selection, shifted by all markdown inserted
                // since the paste was captured (earlier files of the same
                // paste plus earlier pastes that completed meanwhile).
                var total = insertedLengths.get(textarea) || 0;
                var shift = total - base;
                insertAtCaret(textarea, markdown, start + shift, end + shift);
                insertedLengths.set(textarea, total + markdown.length);
            });
        // A failed insertion must not leave the chain rejected, or every
        // later paste for this textarea would silently stop working.
        insertQueues.set(
            textarea,
            task.catch(function () {
                /* insertion errors are non-fatal for later pastes */
            })
        );
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
        // Capture the selection once, at paste time: the user can type or
        // move the caret while the upload runs, and the reference must land
        // where the paste happened, not where the caret ends up.
        var start = typeof target.selectionStart === "number" ? target.selectionStart : 0;
        var end = typeof target.selectionEnd === "number" ? target.selectionEnd : 0;
        var base = insertedLengths.get(target) || 0;
        files.forEach(function (file) {
            if (file.size > MAX_BYTES) {
                showError(target, "Image is too large. The maximum size is 10 MiB.");
                return;
            }
            uploadAndInsert(target, file, start, end, base);
        });
    });
})();
