/* Clipboard image paste for the ticket description editors (JRB-027).
 *
 * A document-level paste listener covers all three ticket-description
 * textareas (new-ticket form, full-page edit form, backlog row-edit modal),
 * which are marked with data-description-editor — delegation means no init
 * wiring is needed for htmx-swapped modal content. An image in the clipboard
 * is uploaded to POST /api/v1/images (separate multipart fetch, never the
 * ticket form) and inserted as a markdown reference at the position captured
 * when the paste happened (the user may type or move the caret while the
 * upload is in flight). Per-textarea work is serialized: images from one
 * paste keep their paste order, and a second paste made while the first is
 * still uploading lands at its own position in the final text — never inside
 * an earlier reference and never re-deleting text an earlier insertion
 * already consumed. Ordinary user edits made while an upload is pending
 * rebase the pending insertions immediately, so a reference also lands at its
 * original position adjusted by every character the user typed or deleted in
 * the meantime. Ordinary text paste passes through untouched. Rejections
 * (unsupported type, too large) surface the server's detail message in the
 * hidden red banner ([data-image-error]) inside the same form.
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
    // - pendingInsertions: the queued-but-not-yet-executed image insertions,
    //   each as { start, end } — the range to replace, or an empty range
    //   (start === end) to insert at. SINGLE-FRAME INVARIANT: these offsets
    //   are always relative to the CURRENT textarea value. Every text
    //   mutation — an ordinary user edit (see the beforeinput/input pairing
    //   below) or one of our own executed image insertions — rebases every
    //   pending insertion immediately, in the very frame the mutation itself
    //   sees. There is no history of mutations and no lazy replay, so paste-
    //   time and execution-time coordinates can never be mixed.
    // - trackedEdits: the 'beforeinput' capture of the user edit currently
    //   in flight ({ start, end, oldLength }), waiting for its 'input' event
    //   to measure the net delta. At most one edit is in flight at a time.
    //   Failed uploads remove their record without touching the text, so
    //   they leave no residue.
    var insertQueues = new WeakMap();
    var pendingInsertions = new WeakMap();
    var trackedEdits = new WeakMap();

    function pendingRecords(textarea) {
        return pendingInsertions.get(textarea) || [];
    }

    function addPendingRecord(textarea, record) {
        var list = pendingInsertions.get(textarea);
        if (!list) {
            list = [];
            pendingInsertions.set(textarea, list);
        }
        list.push(record);
    }

    function removePendingRecord(textarea, record) {
        var list = pendingInsertions.get(textarea) || [];
        var index = list.indexOf(record);
        if (index !== -1) {
            list.splice(index, 1);
        }
    }

    // Rebase every pending insertion through one text change that replaced
    // [replacedStart, replacedEnd) with `netDelta` characters of net new
    // text. Called synchronously with the change: every pending insertion's
    // offsets — and the replaced range — are in the same (pre-change) frame,
    // which is exactly what makes one frame the only frame there is:
    // - An insertion overlapping the replaced range has lost the text it was
    //   going to replace: it collapses to insert-only (start === end) right
    //   after the new text, at the post-change end of the replaced range.
    // - An insertion at or after the replaced range's end shifts by the net
    //   delta: typed or inserted text pushes it forward, deleted text pulls
    //   it back.
    // - An insertion entirely before the replaced range stays put.
    function rebasePendingInsertions(list, replacedStart, replacedEnd, netDelta) {
        var postChangeEnd = replacedEnd + netDelta;
        list.forEach(function (record) {
            if (record.start < replacedEnd && record.end > replacedStart) {
                record.start = postChangeEnd;
                record.end = postChangeEnd;
            } else if (record.start >= replacedEnd) {
                record.start += netDelta;
                record.end += netDelta;
            }
        });
    }

    function uploadAndInsert(textarea, file, record) {
        var body = new FormData();
        body.append("file", file, file.name || "paste.png");
        // From now until this insertion settles, the record stays in the
        // pending list, so user edits rebase it (see the beforeinput/input
        // pairing below).
        addPendingRecord(textarea, record);
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
                    // No text changed, so the pending record must simply
                    // disappear — a failed upload leaves no residue.
                    removePendingRecord(textarea, record);
                    return;
                }
                // Rebase the still-pending insertions through this insertion
                // BEFORE executing it: all of them — and the record's own
                // range — are still in the pre-execution frame, so one pass
                // with the same rules as a user edit (the markdown is the
                // replacement text) keeps every later insertion ordered
                // around the landing position.
                removePendingRecord(textarea, record);
                rebasePendingInsertions(
                    pendingRecords(textarea),
                    record.start,
                    record.end,
                    markdown.length - (record.end - record.start)
                );
                insertAtCaret(textarea, markdown, record.start, record.end);
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
        // Capture the selection once, at paste time — already in the current
        // frame, then kept in that frame by eager rebasing (see the
        // single-frame invariant above): the user can type or move the caret
        // while the upload runs, and the reference must land where the paste
        // happened, not where the caret ends up.
        var start = typeof target.selectionStart === "number" ? target.selectionStart : 0;
        var end = typeof target.selectionEnd === "number" ? target.selectionEnd : 0;
        files.forEach(function (file) {
            if (file.size > MAX_BYTES) {
                showError(target, "Image is too large. The maximum size is 10 MiB.");
                return;
            }
            uploadAndInsert(target, file, { start: start, end: end });
        });
    });

    // While an image insertion is pending, ordinary user edits must rebase
    // the pending insertions too: a paste captured at caret N must land at N
    // in the FINAL text, i.e. adjusted by every character typed or deleted
    // since — not only by the insertions our own code performs. Each edit is
    // captured from its 'beforeinput' event (the selection about to be
    // affected) and measured by pairing it with the following 'input' event
    // (the net length change); the pairing is kept ONLY to compute the
    // affected range and net delta — rebasing itself happens immediately, in
    // the pre-edit frame shared with the pending records. An edit overlapping
    // a pending insertion's range is treated like any other consuming change:
    // the insertion collapses to insert-only right after the replacement
    // text. Tracking is armed only while at least one insertion is pending,
    // so ordinary editing never does any work.
    document.addEventListener("beforeinput", function (event) {
        var target = event.target;
        if (!target || !target.matches || !target.matches("textarea[data-description-editor]")) {
            return;
        }
        if (pendingRecords(target).length === 0) {
            trackedEdits.delete(target);
            return;
        }
        var start = typeof target.selectionStart === "number" ? target.selectionStart : 0;
        var end = typeof target.selectionEnd === "number" ? target.selectionEnd : 0;
        trackedEdits.set(target, { start: start, end: end, oldLength: target.value.length });
    });

    document.addEventListener("input", function (event) {
        var target = event.target;
        if (!target || !target.matches || !target.matches("textarea[data-description-editor]")) {
            return;
        }
        // Only real browser edits carry an inputType: the insertions our own
        // code performs dispatch a plain 'input' Event (no inputType) and
        // must not be recorded again — they already rebase the pending list
        // at execution time.
        if (!event.inputType) {
            return;
        }
        var tracked = trackedEdits.get(target);
        if (!tracked) {
            return;
        }
        trackedEdits.delete(target);
        var netDelta = target.value.length - tracked.oldLength;
        if (netDelta === 0 && tracked.start === tracked.end) {
            return; // Nothing was inserted or deleted.
        }
        rebasePendingInsertions(
            pendingRecords(target), tracked.start, tracked.end, netDelta
        );
    });
})();
