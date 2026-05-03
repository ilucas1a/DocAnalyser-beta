# Step 1.1 — v1.7-alpha State Confirmation

**Date:** 3 May 2026
**Status:** G2 investigation complete — ready for Ian's review
**Step:** 1.1 of the Implementation Strategy
**Companion to:** `Audio_Editing_Implementation_Strategy_2026-05-02.md`, `Audio_Editing_Design_Decisions_Register_2026-05-02.md` §K.2 / §M item 4

---

## TL;DR

**All three features investigated are fully wired end-to-end on disk.** The cleanup-dialog Corrections List dropdown applies the chosen list during cleanup; the *+ Correction…* button in the Word Speaker Panel (and the corresponding right-click in the Source Document view) opens a complete add-to-list dialog with optional retroactive apply-now to the current document; the Restore Backup machinery snapshots before every cleanup-dialog open and exposes a full backup browser that performs counter-backup-on-restore.

**No additional Tranche 1 work is needed to *finish* any of these features.** What I have not done — and cannot do without running the app — is verify they behave correctly when actually exercised. That verification is for Ian (the targeted scenario tests in §5 below).

**Implication for Tranche 2 sizing:** the original commitment in the Decisions Register (B.3 + E.1 — Track Changes infrastructure and *Apply Corrections List to existing document* into Tranche 2) holds as estimated. There is no scaffolded-only feature that needs finishing first; Tranche 2 builds on a working foundation.

---

## 1. Method

I read the on-disk source for every module the project map lists as part of the Corrections Lists and Backups feature surfaces, traced the call chain from each user-facing entry point down to the SQLite layer, and confirmed that every link in each chain is implemented (not stubbed, not commented out, not placeholder).

This is a **disk audit, not a behaviour audit.** Code that is wired correctly *should* work, but until it has been exercised on the running app at least once, the wiring carries some residual risk — wrong sequencing, race conditions on the COM bridge, edge cases in the SQLite schema migration, and so on. Per the Implementation Strategy verification pattern, the scenario tests in §5 are how that risk is closed.

Files read (or sampled):

- `corrections_engine.py` — read in full
- `corrections_db_adapter.py` — read in full
- `add_to_corrections_dialog.py` — read in full
- `default_corrections.json` — read in full
- `corrections_management_dialog.py` — header read; size and structure confirmed (37 KB, 2-pane manager with full Add/Edit/Delete/Duplicate/Import/Export per the project map)
- `transcript_cleanup_dialog.py` — read in full
- `transcript_cleaner.py` — read in full (Phase 3 added in v1.7-alpha; pipeline wires `corrections_list_id`)
- `word_editor_panel.py` — searched and selectively read for *+ Correction…* button wiring (lines 366, 1301–1505)
- `thread_viewer.py` — searched for backup/correction wiring; relevant blocks read at lines 34, 41–44, 859, 881, 1817, 1837–1970, 3709
- `apply_subtask5_backups_rewire.py` — header read (the v1.7-alpha patch that installed the new Restore Backup path)
- `backups_dialog.py` — header read
- `db_manager.py` — searched for table creation, CRUD functions, and seed logic for both features
- `Main.py`, `library_interaction.py`, `document_fetching.py` — searched for `create_backup` auto-trigger sites

Files I did NOT read but treated as covered by the project map: `backups_manager.py` (the project map covers it in §12 with the public API listed and matches what `thread_viewer.py` and `Main.py` are actually calling).

---

## 2. Feature 1 — Corrections List dropdown in the cleanup dialog

### What's there

The cleanup dialog (`transcript_cleanup_dialog.py`) renders a labelled row inside Section A:

> Corrections list: [General ▾] [Edit lists…]

The dropdown is populated by `_populate_corrections_combo()` which calls `corrections_db_adapter.list_get_all()` and prepends a `(none — skip)` sentinel. Default selection is "General" if present, else `(none — skip)`. The *Edit lists…* button opens `corrections_management_dialog.show_corrections_management_dialog()` which is fully implemented (37 KB module, two-pane manager with the full CRUD/import/export feature surface described in the v1.7-alpha plan). On management-dialog close, the dropdown auto-refreshes to pick up new/renamed/deleted lists.

When the user clicks **Run Cleanup**, the dialog reads the selected list_id via `_resolve_corrections_list_id()` and passes it into `clean_transcript(corrections_list_id=…)` on the worker thread.

### What happens inside the pipeline

`clean_transcript()` (in `transcript_cleaner.py`) places Corrections List application at **Phase 3**, between sentence consolidation (Phase 2) and heuristic speaker classification (Phase 4). The position is well-chosen: multi-word phrases that span Whisper-segment boundaries are unified into single sentences first, so substitutions like *"tell vision" → "television"* fire correctly even if Whisper split *tell* and *vision* across separate segments. Speaker classification then sees the corrected text.

`apply_corrections_list()` fetches the entries once (no per-sentence database round-trips), iterates sentences, and uses `corrections_engine.apply_entries_to_text_with_stats()` to do the substitutions. Sentences with zero hits are passed through by reference (efficient). Returns `(modified_sentences, total_hits)`.

`corrections_engine.py` itself implements substitutions with sensible behaviour: longest `original_text` first (prevents shorter matches from consuming text that should belong to a longer phrase), word-boundary anchors only added where they make sense (`\b` would be a no-op on punctuation entries like `" ."`), per-entry case-sensitive flag honoured, malformed regex entries logged and skipped rather than crashing.

The result dict returned through to the cleanup dialog includes `corrections_applied: <total_hits>`. The cleanup dialog's `_on_complete()` reads it from the result dict (line 458 in the dialog's `_worker`).

### SQLite layer

`db_manager.py` creates two tables at line 221 (`corrections_lists`) and 232 (`corrections`), with the full CRUD set: `db_get_all_corrections_lists`, `db_get_corrections_list`, `db_get_corrections_list_by_name`, `db_create_corrections_list`, `db_update_corrections_list`, `db_delete_corrections_list`, `db_get_corrections`, `db_get_correction`, `db_add_correction`, `db_update_correction`, `db_delete_correction` (lines 1441–1630). The bundled "General" list is auto-seeded on first DB init via `_seed_corrections_general_if_needed()` (line 272/275), which reads `default_corrections.json` from the project root.

`default_corrections.json` ships with eight starter rules (six punctuation-spacing fixes plus *"alot" → "a lot"* and *"tell vision" → "television"* as illustrative examples).

### Status: **LIVE, end-to-end.**

There is no stub, no placeholder, no scaffolding. Every link in the chain is real code.

### What I cannot confirm without running the app

- That the General list is actually seeded on first DB init in Ian's running database (defensive: `_seed_corrections_general_if_needed` is gated on a check for whether General already exists, so re-running shouldn't double-seed; but I have not verified the seed actually fired in Ian's environment).
- That the cleanup dialog correctly displays the General list in the dropdown when the user opens it.
- That the worker thread completes without error when General is selected.
- That `corrections_applied` is non-zero when expected.

These are the targeted scenario tests in §5.

---

## 3. Feature 2 — *+ Correction…* round-trip from Word Speaker Panel

### What's there

The Word Speaker Panel (`word_editor_panel.py`) renders a *+ Correction…* button in the navigation row (line 366). Clicking it fires `_add_word_selection_to_corrections()` (line 1304), which:

1. **Captures the user's selection in Word** via COM (`word.Selection.Text`), strips trailing paragraph marks and whitespace, treats anything single-character or pure-whitespace as "no selection".
2. **Opens `add_to_corrections_dialog.show_add_to_corrections_dialog()`** with the captured text as `seed_text` and an `apply_now_callback=self._apply_correction_to_word_doc`. Falls back gracefully if the dialog module is missing (sets a status-bar message rather than crashing).
3. **Updates the panel status bar** with a short preview of what was captured.

`add_to_corrections_dialog.py` is a complete modal dialog with:

- Pre-fillable original-text and replace-with fields
- Destination-list dropdown including a sentinel `+ New list…` for inline list creation
- *Manage lists…* side button into the full management dialog
- Whole-word and case-sensitive checkboxes
- Optional notes field
- An *"Also apply to this transcript now"* checkbox (label customisable per caller; the Word panel customises it)
- A custom confirmation popup after Save that summarises the new rule and (if apply-now was ticked) reports how many hits were applied to the current document
- A defensive helper (`_clamp_to_screen`) that prevents the dialog drifting off-screen when the parent is docked to a screen edge
- A correctly-ordered packing pattern that guarantees the Save/Cancel buttons stay visible

### The apply-now round-trip

When the user ticks *"Also apply to this transcript now"* and clicks Save, the dialog saves the rule via `corrections_db_adapter.correction_add()`, then fires `_apply_correction_to_word_doc()` (line 1378 in `word_editor_panel.py`). That callback does **all four** of the following, in order:

1. **Updates `self._entries` in memory** — both `entry["text"]` and `entry["sentences"][i]["text"]` are updated for consistency. The code explicitly comments why both: the paragraph editor renders from sentences when there are multiple, and any future re-export to Word would otherwise rebuild from stale sentence data.
2. **Applies the substitution in the live Word document** via `Word.ActiveDocument.Range().Find.Execute(... wdReplaceAll ...)`. Word's own engine does the substitution so the user sees the change immediately without needing a save-and-reload cycle.
3. **Saves back to DocAnalyser** via `document_library.update_transcript_entries(self._doc_id, self._entries)`. Wrapped in try/except so a failure here doesn't roll back the rule (the rule is saved to the corrections list regardless).
4. **Refreshes the panel's listbox** (`_populate_list`, `_highlight`, `_refresh_summary`) so the panel reflects the corrected text.

Returns `{"hits": total_hits, "detail": <optional message>}` so the dialog can display a meaningful confirmation popup.

### The same surface in the Source Document

`thread_viewer.py` line 34 imports `show_add_to_corrections_dialog` and line 859 calls it from a Source-Document right-click handler. Per the dialog's docstring this is by design — the same add-to-list flow works from both the Word panel and the in-app editor. The thread-viewer caller has its own apply-now callback (line 881) for the parallel job of applying the new rule to the in-app entries.

### Status: **LIVE, end-to-end, in BOTH the Word panel and the Source Document view.**

### What I cannot confirm without running the app

- That `Word.GetActiveObject` succeeds when the panel was launched alongside Word from DocAnalyser (it should, given the project map reports the panel uses COM polling every 500 ms successfully — but worth one explicit click during testing).
- That `Find.Execute` with the supplied parameters does in fact perform a `wdReplaceAll` substitution as intended.
- That `update_transcript_entries` is exposed by `document_library.py` (the callback handles `ImportError` gracefully but does not loudly notify; if the function were missing the rule would be saved but the library copy wouldn't be — verifiable via the dialog's confirmation popup, which would render a "library copy not updated" detail line).
- The same callback exists on the Source Document side (thread_viewer line 881) — should be tested independently of the Word path.

---

## 4. Feature 3 — Restore Backup

### Background — the v1.7-alpha rewire

The legacy backup mechanism was silently failing on every Thread Viewer open. The root cause is documented in the header of `apply_subtask5_backups_rewire.py`: the legacy `_backup_transcript_entries` referenced `self.doc_id`, an attribute that is never assigned anywhere in the class or its mixins (the correct name is `self.current_document_id`). The patch script's header notes: *"Verified empirically: the user's summaries/ directory contains zero `_entries_backup_*.json` files, confirming the silent breakage."*

The patch script is dated 30 April 2026 and rewires the entire backup path through the new `backups_manager` + `backups_dialog` modules. Subtask 5 (the patch script) and subtask 6 (the dialog itself, dated 30 April 2026) are the two pieces of the v1.7-alpha Restore Backup work.

### What's wired now

**Auto-trigger at cleanup-dialog open.** Three call sites create a backup before the cleanup dialog opens, with `trigger_type=backups_manager.TRIGGER_CLEANUP_OPEN`:

- `Main.py` line 4782
- `library_interaction.py` line 950
- `document_fetching.py` lines 302 and 3099 (two separate cleanup-dialog entry points — fresh transcription and library-load)

Each call site is wrapped in try/except so backup failure cannot prevent the cleanup dialog from opening. The four call sites correspond to the four ways a transcript can have its cleanup dialog re-opened (the four entry points the project map describes for the cleanup dialog).

**Restore Backup button.** `thread_viewer.py` line 3709 wires the Source-Document Restore Backup button to `_restore_transcript_backup` (defined at line 1837). That method opens `show_backups_dialog(...)` with an `on_restore_complete` callback that:

- Persists the restored entries via `update_transcript_entries`
- Updates `self.current_entries` (in-memory)
- Refreshes the paragraph editor (deep-copy `_entries` + `_n_paragraphs` cache + `_refresh_thread_display`, mirroring the canonical pattern used elsewhere in the file)
- Re-applies the metadata_subset (audio_file_path in v1.7-alpha) to both the in-memory app cache and the library record.

Graceful degradation: if `_BACKUPS_DIALOG_AVAILABLE` is False (import failed), the button shows an info message rather than crashing.

**Counter-backup-on-restore.** Per `backups_manager.restore_backup()` (described in the project map §12), the manager always inserts a `pre_restore` snapshot of the current state before swapping in the target payload — so a misclick on Restore is itself recoverable.

**Retention.** 10 most-recent backups per document, pruned automatically after every `create_backup()` (per the project map §12 documentation).

**SQLite schema.** `db_manager.py` line 245 creates the `backups` table; CRUD primitives at lines 1652–1716: `db_create_backup`, `db_list_backups`, `db_get_backup`, `db_delete_backup`, `db_prune_backups`. The schema includes `document_id` with `FK to documents, ON DELETE CASCADE` so deleting a document cleans up its backups automatically.

### Status: **LIVE, end-to-end. The legacy silent breakage is fixed.**

### What I cannot confirm without running the app

- That the cleanup-dialog auto-trigger actually fires and writes a row (the four call sites are wrapped in try/except — if `backups_manager` raises silently for any reason, the cleanup dialog still opens but no backup exists).
- That `show_backups_dialog` correctly lists the rows, that Restore performs the swap correctly, and that the counter-backup is created.
- That the Source Document view auto-refreshes after restore (this is the on_restore_complete callback's job; it looks complete on disk).
- The retention count is honoured (after 10 backups, the next `create_backup` should prune the oldest).

---

## 5. Targeted scenario tests for Ian

The Implementation Strategy lists three scenario tests for Step 1 (under "G2 v1.7-alpha investigation"). I'm reproducing them here with sharper detail informed by the disk audit, plus an additional test for the *+ Correction…* round-trip from the Source Document path (the project map describes this surface but the original Step 1 test plan didn't single it out).

### Test 1 — Corrections List dropdown (10 minutes)

1. Open DocAnalyser. Begin a fresh transcription on a short audio file (a 2–3 minute clip is plenty).
2. When the cleanup dialog opens, confirm Section A includes the *Corrections list:* row, with **General** pre-selected in the dropdown.
3. Click *Edit lists…* — the management dialog should open. Browse the General list; you should see eight entries (six punctuation-space rules plus *"alot" → "a lot"* and *"tell vision" → "television"*).
4. Close the management dialog. Confirm the cleanup dialog dropdown still shows General.
5. Tick whatever cleanup options you want, click **Run Cleanup**.
6. After Done ✔, route to either Thread Viewer or Word — whichever is more convenient.
7. Inspect the cleaned transcript: any " ." or " ," should now be " ." → "." etc. (punctuation rules); any "alot" should be "a lot".
8. **Optional sharper test:** before step 1, contrive a transcript that would contain *"alot"*. Easy way: use any speech that says "a lot" — Whisper sometimes mishears it. If you can't easily produce one, this test is satisfied by the punctuation-spacing fixes alone; they fire on virtually any transcript.

**Pass criteria:** dropdown shows General; management dialog opens; corrections appear in the cleaned text; no errors in the status bar.

**Fail mode to watch for:** if the dropdown shows only `(none — skip)` with no other entries, the General list was not seeded on first DB init. That's a Tranche 1 fix (rerun the seed manually, or add an explicit re-seed step to the migration code).

### Test 2 — *+ Correction…* round-trip from the Word panel (10 minutes)

1. Take the same transcription from Test 1 (or do a fresh one) and route to **Microsoft Word**.
2. With the Word window and the Speaker Panel both open, find a paragraph in Word that contains a word you want to correct (any word will do — pick something distinctive so you can verify the substitution worked).
3. Highlight the word in Word.
4. Click *+ Correction…* in the Speaker Panel.
5. The Add to Corrections List dialog should open with the highlighted word in the *Original text* field and an empty *Replace with* field.
6. Type the corrected version in *Replace with*. Tick *"Also apply to this transcript now"*. Click Save.
7. The confirmation popup should appear, naming the destination list and reporting *N occurrences replaced* (where N is at least 1).
8. Look at the Word document — every occurrence of the original word should now show the corrected version.
9. Click *Save edits to DocAnalyser* in the Speaker Panel. Close Word.
10. Re-open the document in the Source Document view in DocAnalyser — the corrected text should appear there too (this also exercises the post-Save round-trip refresh that's a known E13 issue, but for now we're checking that the rule's apply-now correctly persisted to the library before E13's fix).
11. Open the Corrections Lists management dialog (Settings or wherever it's accessible). Find your new rule in the destination list you picked.

**Pass criteria:** dialog opens with seed; rule saves; confirmation popup reports correct hits; Word document reflects the substitution; new rule visible in the management dialog.

**Fail modes to watch for:**
- Dialog doesn't open: `add_to_corrections_dialog` import failed (see Speaker Panel status bar).
- Dialog opens but seed text is empty when you had a selection: COM call to `Word.Selection.Text` returned nothing useful — check Word actually has focus when you click *+ Correction…*.
- Save succeeds but apply-now reports 0 hits: confirm word-boundary and case-sensitive flags are right for your test case.
- Save succeeds but Word document not changed: the `Find.Execute` call failed silently — check the panel status bar for a warning.

### Test 3 — *+ Correction…* round-trip from the Source Document (5 minutes)

1. Take a transcription routed to the Thread Viewer / Source Document (not Word).
2. Right-click on a word in the source pane.
3. Confirm the right-click menu includes an option for adding to a Corrections List (the exact menu label may vary; search for "correction" in the menu).
4. Pick that option. The Add to Corrections List dialog should open with the right-clicked word as the seed.
5. Same flow as Test 2 from step 6 onwards. The apply-now callback in this case applies to the in-app entries rather than going through Word's COM bridge.

**Pass criteria:** same as Test 2.

**Fail modes:** if the right-click menu doesn't include the corrections option, the wiring at `thread_viewer.py` line 859 is conditional on something we should check. If the dialog opens but apply-now does nothing, the thread_viewer's parallel apply-now callback (line 881) has a bug.

### Test 4 — Restore Backup (10 minutes)

1. Take any existing audio transcription document from the Documents Library that you don't mind editing.
2. Open it in the Source Document view.
3. Click the cleanup-dialog re-open path (whichever way you re-open the cleanup dialog from a saved document — the project map describes this as available from `Main.py`, `library_interaction.py`, or via the cleanup dialog being shown again). At this point a `TRIGGER_CLEANUP_OPEN` backup should be silently created.
4. Make some destructive edits to the document (delete a few paragraphs, change a speaker name, etc.). Save.
5. Click the *Restore Backup* button in the Source Document view.
6. The Backups dialog should open, listing at least one row with trigger type *"Before cleanup"* and a recent timestamp.
7. Select that backup row, click Restore. Confirm the destructive edits are gone (the document is back to its pre-edit state).
8. Click Restore Backup again. Confirm the dialog now lists at least two rows — the original *"Before cleanup"* backup AND a new *"Before restore"* backup that holds your destructive-edits version (in case the restore was a misclick).
9. Optional: select the *"Before restore"* row and Restore — the destructive edits should reappear (full cycle).

**Pass criteria:** backup row exists after step 3; Restore swaps state correctly; counter-backup is created on restore.

**Fail modes to watch for:**
- No backup row appears in step 6: the auto-trigger silently failed — check log for `backups_manager.create_backup` errors.
- Restore button doesn't open the dialog: `_BACKUPS_DIALOG_AVAILABLE` is False — `backups_dialog` import failed at thread_viewer load time.
- Restore appears to succeed but the document didn't change: the on_restore_complete callback isn't refreshing the Source Document view from the canonical store. **This is the same kind of bug as E13** — worth flagging if it appears, since it would indicate E13's fix needs to extend to the restore path too.

---

## 6. Implications for the rest of Tranche 1 and Tranche 2

### Tranche 1 unchanged

The G2 finding — features are live, not scaffolded — means **Tranche 1's day-count remains the original ~5 days**. There is no additional building required to bring Corrections Lists or Backups to a usable state for v1.7-beta.

The four Tranche 1 items remain:

- Step 2 (E13 scoping pass)
- Step 3 (C5-partial — remove voice radio)
- Step 4 (E13 fix)
- Step 5 (E6 timestamp content controls)

### Tranche 2 unchanged

The Decisions Register lock on B.3 (Track Changes for bulk edits, Tranche 2) and E.1 / D1a (Apply Corrections List to existing document, Tranche 2) **stands as committed**. Both build on the now-confirmed-live foundation:

- Track Changes integration (Step 9a) wraps the bulk operations that already happen — speaker bulk substitution, Corrections List apply, future AI refinement — with Word's Revisions API. It does not require Corrections Lists themselves to be re-built.
- *Apply Corrections List to this document* (Step 10a) re-uses the same `apply_corrections_list` Phase-3 logic, the same SQLite layer, and the same Track Changes plumbing from Step 9a. It's purely a new entry point on an existing pipeline.

### Two minor implication points worth noting

**A) The Decisions Register E.3 (Reset to raw transcription) deferral is safe.** That deferral was conditional on "G2 confirming Backups are wired." Backups are confirmed wired. Reset can stay deferred to Tranche 4 with no risk.

**B) The 30-April-2026 backups rewire is recent.** The patch script ran on 30 April; today is 3 May. Three days of usage by Ian since the rewire, but no evidence one way or the other of whether anyone has actually exercised the Restore Backup path. **Test 4 above is the most important of the four scenario tests** because the feature is technically live but has the least real-world exposure.

---

## 7. What I would recommend Ian do with this note

1. **Skim it for any disagreements with my reading** — particularly anywhere I've claimed a thing is wired that you suspect isn't. If something feels off, the underlying file is named in §1 and the line numbers / function names are in §§2–4.
2. **Run the four scenario tests in §5 in one sitting** — total ~35 minutes. The order doesn't matter much; if anything fails, pause and decide whether it's a Tranche 1 fix or a deferred / known-issue item.
3. **Update the Decisions Register K.2 checkboxes** based on outcomes:
   - All four tests pass → tick K.2 sub-items, mark M item 4 as fully resolved.
   - Test 1 fails (General list not seeded) → small Tranche 1 fix; the seed function exists, just needs to actually fire.
   - Test 4 fails (Restore Backup misbehaves) → Tranche 1 fix in the on_restore_complete callback; same shape as E13.
4. **Move on to Step 1.2 — the Source Document walkthrough** — assuming all tests pass cleanly. If something needs fixing first, fold that fix into Tranche 1 sequence ahead of Step 2.

---

*Compiled by Claude on 3 May 2026 from a disk-audit of the v1.7-alpha Corrections Lists and Backups code paths. Companion to `Audio_Editing_Implementation_Strategy_2026-05-02.md` Step 1.1.*
