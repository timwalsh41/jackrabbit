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
 * still uploading has its paste-time position transformed by the completed
 * insertions recorded since — ones that landed at or before it shift it by
 * their net text change (inserted minus deleted), and one that consumed
 * (part of) its paste-time selection collapses it to an insert-only reference
 * placed right after that insertion — so concurrent pastes keep their
 * paste-time positions relative to the final text without landing inside an
 * earlier reference or re-deleting consumed text. Ordinary
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
    // - insertions: every completed insertion as
    //   { execStart, execEnd, insertedLength, deletedLength, affectsFrom,
    //   pasteStart, pasteEnd }: the executed range its reference now occupies
    //   (measured in the text state of its own execution, so already
    //   including every earlier entry's effect), how much text it inserted
    //   and deleted (its net text change), `affectsFrom` — the paste-time
    //   offset from which that net change applies (the end of the replaced
    //   selection, or the insertion point when nothing was deleted) — and
    //   the paste-time selection as captured. Failed insertions record
    //   nothing. Each paste captures the array length at paste time; when
    //   its turn comes, its paste-time selection is transformed by the
    //   entries recorded since its capture (see adjustedInsertPosition).
    var insertQueues = new WeakMap();
    var insertions = new WeakMap();

    // Transform a queued insertion's paste-time selection [start, end) into
    // the current-text positions to use when its turn comes, given the
    // completed insertions recorded since the paste was captured. Walking the
    // entries in execution order:
    // - An entry whose change applies at or before the selection
    //   (affectsFrom <= start) shifts both offsets by its net text change
    //   (inserted minus deleted): a plain insertion pushes forward by its
    //   length, a replacement by its length minus the replaced span. An
    //   entry that landed after the selection (pasteStart >= end) has no
    //   effect.
    // - An entry whose paste-time selection overlaps [start, end) consumed
    //   (wholly or partly) the selection this paste was going to replace:
    //   there is nothing left to delete, so the queued insertion collapses
    //   to insert-only immediately after that entry's executed range. Its
    //   execEnd already includes every earlier entry's effect, so the
    //   accumulated shift is not added again; the entry's own net change is
    //   likewise not applied (anchoring after its executed end already
    //   accounts for it). Later entries whose change applies at or before
    //   the collapse point still move it forward, keeping paste order.
    function adjustedInsertPosition(completed, firstIndex, start, end) {
        var shift = 0;
        var collapse = null; // { at: insertion point, origin: paste-time point } once consumed
        for (var i = firstIndex; i < completed.length; i++) {
            var entry = completed[i];
            var overlaps = entry.pasteStart < end && entry.pasteEnd > start;
            if (collapse !== null) {
                if (entry.affectsFrom <= collapse.origin) {
                    collapse.at += entry.insertedLength - entry.deletedLength;
                }
            } else if (overlaps) {
                collapse = { at: entry.execEnd, origin: entry.pasteEnd };
            } else if (entry.affectsFrom <= start) {
                shift += entry.insertedLength - entry.deletedLength;
            }
        }
        if (collapse !== null) {
            return { start: collapse.at, end: collapse.at, collapseOrigin: collapse.origin };
        }
        return { start: start + shift, end: end + shift, collapseOrigin: null };
    }

    function uploadAndInsert(textarea, file, start, end, capturedCount) {
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
                var completed = insertions.get(textarea) || [];
                var adjusted = adjustedInsertPosition(completed, capturedCount, start, end);
                insertAtCaret(textarea, markdown, adjusted.start, adjusted.end);
                completed.push({
                    execStart: adjusted.start,
                    execEnd: adjusted.start + markdown.length,
                    insertedLength: markdown.length,
                    deletedLength: adjusted.end - adjusted.start,
                    affectsFrom:
                        adjusted.collapseOrigin !== null
                            ? adjusted.collapseOrigin
                            : adjusted.end > adjusted.start ? end : start,
                    pasteStart: start,
                    pasteEnd: end
                });
                insertions.set(textarea, completed);
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
        var capturedCount = (insertions.get(target) || []).length;
        files.forEach(function (file) {
            if (file.size > MAX_BYTES) {
                showError(target, "Image is too large. The maximum size is 10 MiB.");
                return;
            }
            uploadAndInsert(target, file, start, end, capturedCount);
        });
    });
})();
