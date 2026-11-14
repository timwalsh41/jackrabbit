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
 * earlier reference or re-deleting consumed text. Ordinary user edits made
 * while an upload is pending are recorded in the same list of text mutations,
 * so the reference also lands at its original caret adjusted by every
 * character the user typed or deleted in the meantime. Ordinary text paste
 * passes through untouched. Rejections (unsupported type, too
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
    // - mutations: every recorded text change, in execution order, as
    //   { pasteStart, pasteEnd, affectsFrom, netDelta, execEnd }: the
    //   paste-time range the change consumed or affected, `affectsFrom` — the
    //   paste-time offset from which its net text change applies (the end of
    //   the replaced/affected selection, or the insertion point when nothing
    //   was deleted) — `netDelta`, the change's net text change (inserted
    //   minus deleted), and `execEnd`, the executed range end in the text
    //   state of the change's own execution (so already including every
    //   earlier entry's effect). Two kinds of change share the list:
    //   completed image insertions and ordinary user edits made while at
    //   least one insertion is pending (tracked via beforeinput/input, see
    //   below). Failed insertions and edits while nothing is pending record
    //   nothing. Each paste captures the list length at paste time; when its
    //   turn comes, its paste-time selection is transformed by the entries
    //   recorded since its capture (see adjustedInsertPosition).
    // - pendingInsertions: how many uploads are still in flight for this
    //   textarea — the window during which user edits are recorded.
    // - trackedEdits: the 'beforeinput' capture of the user edit currently
    //   in flight ({ start, end, oldLength }), waiting for its 'input' event
    //   to measure the net delta. At most one edit is in flight at a time.
    var insertQueues = new WeakMap();
    var mutations = new WeakMap();
    var pendingInsertions = new WeakMap();
    var trackedEdits = new WeakMap();

    function mutationList(textarea) {
        var list = mutations.get(textarea);
        if (!list) {
            list = [];
            mutations.set(textarea, list);
        }
        return list;
    }

    function pendingCount(textarea) {
        return pendingInsertions.get(textarea) || 0;
    }

    // Record one text change in paste-time coordinates (see `mutations`).
    function recordMutation(textarea, start, end, affectsFrom, netDelta, execEnd) {
        mutationList(textarea).push({
            pasteStart: start,
            pasteEnd: end,
            affectsFrom: affectsFrom,
            netDelta: netDelta,
            execEnd: execEnd
        });
    }

    // Transform a queued insertion's paste-time selection [start, end) into
    // the current-text positions to use when its turn comes, given the text
    // mutations recorded since the paste was captured — completed image
    // insertions and, because an upload does not pause ordinary typing, user
    // edits recorded while the upload was pending. The selection is walked
    // through the entries in execution order; since every text change is
    // recorded while an insertion is pending, the selection and each entry
    // share one text frame at each step (the entry's coordinates are the
    // state its own execution found, and the selection has been transformed
    // by every entry before it):
    // - An entry whose change applies at or before the selection
    //   (affectsFrom <= start) shifts both offsets by its net text change:
    //   a plain insertion or typed characters push forward by their length,
    //   a replacement or deletion by its net delta (negative when text
    //   shrank). An entry that landed after the selection (pasteStart >=
    //   end) leaves it where it is.
    // - An entry whose paste-time range overlaps [start, end) consumed
    //   (wholly or partly) the selection this paste was going to replace:
    //   there is nothing left to delete, so the queued insertion collapses
    //   to insert-only immediately after that entry's executed range — the
    //   same treatment for an overlapping user edit as for an overlapping
    //   image insertion. The collapse point starts at that execEnd (already
    //   in the frame after the entry, so the entry's own net change is not
    //   applied again) and later entries whose change applies at or before
    //   it still move it forward, keeping order.
    function adjustedInsertPosition(recorded, firstIndex, start, end) {
        var collapse = null; // { at: insertion point, origin: paste-time point } once consumed
        for (var i = firstIndex; i < recorded.length; i++) {
            var entry = recorded[i];
            var overlaps = entry.pasteStart < end && entry.pasteEnd > start;
            if (collapse !== null) {
                if (entry.affectsFrom <= collapse.origin) {
                    collapse.at += entry.netDelta;
                    collapse.origin += entry.netDelta;
                }
            } else if (overlaps) {
                collapse = { at: entry.execEnd, origin: entry.pasteEnd };
            } else if (entry.affectsFrom <= start) {
                start += entry.netDelta;
                end += entry.netDelta;
            }
        }
        if (collapse !== null) {
            return { start: collapse.at, end: collapse.at, collapseOrigin: collapse.origin };
        }
        return { start: start, end: end, collapseOrigin: null };
    }

    function uploadAndInsert(textarea, file, start, end, capturedCount) {
        var body = new FormData();
        body.append("file", file, file.name || "paste.png");
        // From now until this insertion settles, user edits on this textarea
        // must be recorded so they can rebase the captured selection.
        pendingInsertions.set(textarea, pendingCount(textarea) + 1);
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
                try {
                    if (markdown === null) {
                        return;
                    }
                    var adjusted = adjustedInsertPosition(
                        mutations.get(textarea) || [], capturedCount, start, end
                    );
                    insertAtCaret(textarea, markdown, adjusted.start, adjusted.end);
                    recordMutation(
                        textarea,
                        start,
                        end,
                        adjusted.collapseOrigin !== null
                            ? adjusted.collapseOrigin
                            : adjusted.end > adjusted.start ? end : start,
                        markdown.length - (adjusted.end - adjusted.start),
                        adjusted.start + markdown.length
                    );
                } finally {
                    pendingInsertions.set(textarea, pendingCount(textarea) - 1);
                }
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
        var capturedCount = mutationList(target).length;
        files.forEach(function (file) {
            if (file.size > MAX_BYTES) {
                showError(target, "Image is too large. The maximum size is 10 MiB.");
                return;
            }
            uploadAndInsert(target, file, start, end, capturedCount);
        });
    });

    // While an image insertion is pending, ordinary user edits must rebase
    // the pending paste's captured selection too: a paste captured at caret N
    // must land at N in the FINAL text, i.e. adjusted by every character
    // typed or deleted since — not only by the insertions our own code
    // performs. Each edit is captured from its 'beforeinput' event (the
    // selection about to be affected) and measured by pairing it with the
    // following 'input' event (the net length change), so the record carries
    // the same shape as an image insertion's. An edit overlapping a captured
    // selection is treated like a consumed selection: adjustedInsertPosition
    // collapses the pending paste to insert-only right after the edit's
    // executed range. Tracking is armed only while at least one insertion is
    // pending, so ordinary editing never accumulates records.
    document.addEventListener("beforeinput", function (event) {
        var target = event.target;
        if (!target || !target.matches || !target.matches("textarea[data-description-editor]")) {
            return;
        }
        if (pendingCount(target) === 0) {
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
        // code performs dispatch a plain 'input' Event and are recorded
        // separately, with their own paste-time coordinates.
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
        // The edit replaces [start, end) with text netDelta longer, so its
        // executed end is end + netDelta and its change applies from end.
        recordMutation(
            target,
            tracked.start,
            tracked.end,
            tracked.end,
            netDelta,
            tracked.end + netDelta
        );
    });
})();
