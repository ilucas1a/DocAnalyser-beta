# Audio Editing Walkthrough — Parking Lot

**Date:** 2 May 2026
**Status:** Action items captured during the audio-editing walkthrough session of 2 May 2026
**Source:** Walkthrough conversation between Ian and Claude, 2 May 2026
**Companion to:** `Roadmap/Audio_Editing_Inventory_2026-05-01.md`

---

## How to read this document

Each item is something the walkthrough surfaced as needing action before packaging — or, where flagged, as a deliberate decision to defer. Items are grouped by theme rather than by the order they came up in the conversation.

Priority indicators:
- 🔴 High — affects naive-user comprehension or risks data loss; should be done before packaging
- 🟡 Medium — meaningful improvement, do soon
- 🟢 Low — nice to have, can wait
- 🔵 Decision — needs a call before any work

---

## A. Settings and preferences

**A1. 🟡 Audio & Transcription Settings dialog — compactness pass.** Currently cluttered. Specific lever: collapse the API keys panel into dropdowns or an expandable section. Likely other density wins available too. First impression for new Faster-Whisper users — knock-on effects on Stage 2 confusion throughout the rest of the workflow.

**A2. 🔴 "Edit in Word by default" preference.** New preference in Audio & Transcription Settings: *"When transcription completes, edit in Word"*.

When set:
- Transcription completes → cleanup dialog opens automatically with the Source Document populated and visible behind it.
- The cleanup dialog shows Section A and Section B as normal, but the bottom of the dialog has only a single action button — *"Run Cleanup and open in Word"* (or *"Skip cleanup and open in Word"*). No routing choice presented; the user has pre-decided.
- On clicking, the dialog closes, cleanup runs (or is skipped), and Word + companion player + speaker panel open together.

When not set: current behaviour preserved (routing buttons appear after cleanup).

**Open sub-question for tomorrow:** When the preference is set, does the user need an escape hatch to override it for a single document? Two options: (a) hard preference — they'd have to change Audio Settings; (b) soft preference — small *"Open in Source Document instead"* link in the cleanup dialog. (b) is friendlier; (a) is simpler.

**A3. 🟡 "Show bulk edits as tracked changes" preference.** New preference in Audio & Transcription Settings: *"Show bulk edits as tracked changes for review"*, default on. Affects: applying Corrections Lists, bulk speaker substitution (*Apply names to whole document*), future AI refinement actions, and the planned post-hoc *"Apply Corrections List to this document"* action (item D1a).

The principle: when a single user action causes many text changes, the user should have the chance to review before committing. Track Changes is Word's native mechanism for this and gives the user accept/reject controls per-change or wholesale. Implementation requires DocAnalyser to use Word's Revisions API rather than direct text manipulation — non-trivial but builds on existing COM infrastructure in the Speaker Panel. May also live as a per-action choice on each bulk button (*Apply with track changes* / *Apply directly*).

This may be the strongest single argument for not packaging without v1.7-alpha — bulk edits become a much bigger safety question once Corrections Lists are live.

---

## B. Documents Library and lifecycle

**B1. 🟡 Documents Library entry during transcription.** Currently the recording does not appear in the library until transcription completes. Add an entry at the moment "Load" is clicked, with a *"Transcribing… (X% / elapsed time)"* status visible in the library tree. Status updates can mirror the existing main-window status line. On completion: transitions to a normal document entry. On failure: transitions to an error state the user can re-trigger from. Folder placement: probably the default folder unless configured otherwise.

---

## C. The cleanup dialog (the big one)

**The cleanup dialog is the heaviest single piece of work in the parking lot, and the highest-stakes for naive users — it's the one screen every audio user sees.**

**C1. 🔴 Top-of-dialog wording.** Replace *"N segments transcribed. Choose options below."* with something like *"Your 1h 34m transcription is ready. Choose how to clean it up:"* — drops the technical *"segments"*, gives the user duration in meaningful units, gives a clear next-action verb.

**C2. 🟡 "Listener back-channels" reworded.** Candidate: *"Keep brief listener responses (mm-hmm, right, yeah) as [annotations]"*. Or: *"Keep brief acknowledgments (mm-hmm, right) as [annotations] — useful for preserving conversational rhythm in oral history."* Decision tomorrow.

**C3. 🔴 "Skip — assign manually later" reworded.** Currently ambiguous about what happens to paragraphing. Plain-English version: *"Skip — paragraphs will be created normally but without speaker labels. You can assign speakers in Word or in DocAnalyser later."*

**C4. 🟡 "Suggest speakers automatically (heuristic, provisional)" reworded.** Currently cryptic. Candidate help-popup wording:

> *"Suggest speakers automatically — DocAnalyser will guess who's speaking based on patterns in the text (questions tend to come from the interviewer, longer answers from the interviewee). You should review the suggestions before relying on the result."*

**C5. 🔴 Section B becomes engine-aware.** Speaker-detection-by-voice removed as a cleanup-dialog choice — it's a property of the transcription engine, not of cleanup. Three states:

- **AssemblyAI with diarisation ticked** → no radio choice; Section B reads *"Speakers identified by AssemblyAI — assign names below"*, Section C is the naming step.
- **AssemblyAI without diarisation, or any local engine** → two radios: Skip and Suggest speakers automatically.
- **OpenAI Whisper cloud** → same as second case (no diarisation), two radios.

**The current "Detect speakers by voice (not available — see Help for setup)" wording must not ship under any disposition.** The *"see Help for setup"* suffix actively misleads users into hunting for setup steps that don't exist.

**C6. 🔴 Help icons throughout the dialog.** A (?) icon next to each section heading and each radio option, opening a tooltip or popup with one or two plain-English sentences. Specific targets:

- Section A heading — what cleanup does, when to skip it.
- Each Section A checkbox — what each option does.
- Section B heading and each radio — what each path produces.
- Edit Lists button — what a Corrections List is, what it does for the user. The Vietnam-veterans 30-interviews example would be a great concrete illustration.

**C7. 🟢 Naming sweep — engineer terms vs user terms.** "Segments", "resolved/unresolved", "heuristic", "provisional", "back-channels" — same mental error throughout the UI. Worth a wider sweep beyond the cleanup dialog for similar engineer-leaking-into-UI terms. (See item E2 for the resolved/unresolved replacement.)

---

## D. Post-hoc cleanup adjustments

**D1. 🟡 Post-hoc cleanup actions on already-processed transcripts.** Currently no way to re-trigger cleanup or apply individual cleanup steps after the initial run. Three sub-items in priority order:

- **D1a. 🔴 "Apply Corrections List to this document"** — most valuable, addresses the case where a Corrections List didn't exist when this document was first processed. Should respect the Track Changes preference (item A3). Will be heavily used once Corrections Lists are live.
- **D1b. 🟡 "Re-suggest speakers"** — re-runs heuristic Phase 3 on existing paragraphs without rebuilding them.
- **D1c. 🔵 "Reset to raw transcription"** — full-redo case, with strong confirmation dialog. Decide tomorrow whether this is worth building or whether the existing "delete and re-import" path is sufficient.

---

## E. Word editing view

**The Word editing view is the highest-stakes onboarding moment in the entire app. It is where users will spend most of their actual editing time, and getting them productive here determines whether they stick with DocAnalyser.**

**E1. 🔴 Welcome overlay on first open of the Speaker Panel.** Modal sitting over the Panel on first open, explaining the three-window arrangement, the user's goal in this view, and where to start. *Don't show again* tickbox. Links to a fuller help document (item E5).

**E2. 🔴 Speaker Panel — naming sweep.** Replace *"304 paragraphs · 0 resolved · 304 unresolved"* with plain-English equivalent: *"304 paragraphs · 0 named · 304 yet to be named"*. *Prev unresolved* / *Next unresolved* buttons rename to *Prev unnamed* / *Next unnamed*.

**Important caveat surfaced during walkthrough:** *"named"* is itself a slightly misleading term — after *Apply names to whole document* runs, every paragraph reads *named* even though many of the names may be wrong (the heuristic guessed). *"Named"* tracks whether a paragraph has *a* speaker label; it does not track whether that label is *correct*. The status line cannot communicate correctness without verification (which only the user can supply, by listening). One option to consider: an additional state — *verified* — that the user can mark per paragraph after they've listened and confirmed the assignment. Three states then: *yet to be named* → *named (unverified)* → *verified*. The display becomes e.g. *"304 paragraphs · 12 verified · 292 unverified · 0 yet to be named"*. This adds tracking machinery but gives the user a way to see real progress through the document. To decide tomorrow whether worth building.

**E3. 🟡 Speaker Panel — colour scheme.** Current dark background with low-contrast text is jarring against the rest of DocAnalyser's light UI and is harder to read. Experiment with light-background variant. Accessibility benefit: dark themes with low-contrast white text are a known accessibility issue.

**E4. 🔴 Help icons throughout the Speaker Panel.** Same pattern as item C6 — (?) icons next to every major control. Roughly a dozen targets, each needing one or two plain-English sentences:

- The named/yet-to-be-named stats line
- The audio block (double-click to seek)
- The speaker names block
- *+ Add speaker*
- *Assign* vs *Apply names to whole document*
- *Prev unnamed* / *Next unnamed*
- *Refresh ¶*
- *Correction…*
- *Whole doc / This ¶* timestamp toggles
- *Show all / Hide secondary / Hide all* timestamp visibility
- *Save edits to DocAnalyser* (the persistence moment — closing Word without it loses work)

**E5. 🔴 "Editing transcripts in Word" help document.** Short help-menu entry covering the editing taxonomy with examples (item F1), the dependencies between editing categories in suggested order, and the Word path's hidden constraints (item E6). Two screens of plain prose. Linked from the welcome overlay.

**E6. 🔴 Word path — make `[MM:SS]` timestamps non-deletable. HIGHEST PRIORITY BEFORE PACKAGING.** The current "warn the user not to delete timestamps" approach is weaker than making it impossible. **Confirmed during walkthrough: timestamps can be deleted with a single keystroke and Word offers no resistance** — every user can trigger this failure trivially. Render `[MM:SS]` (and the secondary sentence-level `{MM:SS}` markers within paragraphs) as Word content controls marked "cannot be deleted, cannot be edited". Standard Word machinery; eliminates the timestamp-orphan failure mode entirely. Splits and merges still work because they operate on paragraph boundaries, not on timestamp content.

**E7. 🔴 Split/merge confirmation dialogs (first-time, dismissable) and sentence-boundary snap.**

*Split rule — cursor sentence becomes first sentence of new paragraph.* Walkthrough surfaced the mid-sentence-split failure mode: pressing Enter mid-sentence breaks the paragraph wherever the cursor is, leaving incoherent half-sentences in both paragraphs and orphaning the secondary `{MM:SS}` timestamp from its anchor. **Splits must only happen at sentence boundaries, and the rule must be unambiguous: the sentence containing the cursor always becomes the first sentence of the new paragraph.** Pressing Enter anywhere within a sentence — start, middle, end — produces the same result: that sentence moves to the new paragraph, taking its `{MM:SS}` anchor with it as the new paragraph's `[MM:SS]` header. One rule, applied uniformly, no sub-cases for the user to reason about.

*Split dialog.* User presses Enter inside a paragraph. Dialog appears: *"Do you wish to create a new paragraph? The new paragraph will start with the sentence beginning '…first few words of the sentence…' at [MM:SS]."* Yes / No / *Don't show again for splits*. The dialog showing the user the proposed sentence is what catches the case where the user is one sentence away from where they wanted to be — they cancel, reposition, and try again. Yes performs the split.

*Speaker inheritance on split.* The new paragraph inherits the originating paragraph's speaker assignment. The user then re-assigns it via the Speaker Panel if the new paragraph belongs to a different speaker (which is often the reason they're splitting in the first place). Confirmed during walkthrough as the correct behaviour.

*Merge dialog.* User deletes a paragraph break. Dialog appears: *"This will merge the two paragraphs. The merged paragraph will keep the speaker assigned to the paragraph above. Do you wish to continue?"* Yes / No / *Don't show again for merges*. Yes performs the merge.

The merge dialog is higher-value than the split dialog because the merge case carries silent-data-loss risk (one speaker label is lost on merge). Separate *Don't show again* flags for splits vs merges so users can dismiss the lower-value one while keeping the higher-value one.

**E8. 🟡 Speaker Panel — *Assigned X to para N* footer message.** Two improvements: (a) replace *"para N"* with friendlier wording — *"first paragraph"*, or echo the visible `[MM:SS]` timestamp. (b) Confirm the message persistence behaviour is right (visible long enough to see; not so long it's noise).

**E9. 🟡 Speaker Panel — clarify *Assign* vs *Apply names to whole document* relationship.** Help-icon copy needs to explain *when to use each*: per-paragraph for cases where the heuristic mis-labelled some paragraphs (so bulk substitution would propagate the error) or where the user wants to verify before committing to all paragraphs; bulk for cases where labels are correct and only names need substituting. Resolved during walkthrough: single-click on a Paragraphs list row navigates the Word cursor and seeks audio (and plays) — see E11 on discoverability.

**E10. 🔴 Speaker Panel — *Apply names to whole document* with Track Changes review.** When item A3 (Track Changes preference) is on, *Apply names to whole document* writes the substitutions as tracked changes rather than committing them directly. The user can then review per-paragraph (accepting where the heuristic was right, rejecting where it was wrong) using Word's standard reviewing UI — right-click Accept/Reject, or the Review ribbon. Rejected changes revert the paragraph to its `[SPEAKER_X]` placeholder; the user can then assign the correct name per-paragraph via the Speaker Panel. This subsumes the need for a separate "undo bulk apply" mechanism. Strengthens the case for A3 being a default-on feature rather than a power-user option.

**Refinement on save behaviour.** When the user clicks *Save edits to DocAnalyser* with unresolved tracked changes still present, DocAnalyser should refuse to save and prompt the user to resolve them first — *"You have N unresolved tracked changes. Please accept or reject each one before saving."* Saving with unresolved revisions creates ambiguity about what was actually committed.

**E11. 🟡 Speaker Panel — Paragraphs list double-click discoverability.** The double-click-to-seek behaviour is correct (single-click would be too noisy if every cursor movement triggered audio playback) but discoverability is poor — a naive user reasonably expects single-click. Existing instruction *"(double-click to play & navigate)"* is in small parenthetical text at the top of the section, easy to miss. Two improvements: (a) lighter Speaker Panel theme (item E3) would naturally make the instruction more visible; (b) add an on-hover tooltip on the Paragraphs list area: *"Double-click any row to seek the audio and play."* Pairs with help-icon copy in E4.

**E12. 🟢 Refresh ¶ button — confirmed as rare-edge-case only.** Walkthrough confirmed that the Speaker Panel auto-updates correctly after splits via COM polling — a paragraph split in Word produces an immediate update to the Paragraphs list and the resolved/unresolved counter. Refresh ¶ is therefore needed only in edge cases (rapid edits, clipboard operations, async issues), not for routine user actions. Good news for naive users — one less piece of hidden knowledge. Help-icon copy for Refresh ¶ (item E4) should reflect this: *"Re-sync the panel with Word if you notice a mismatch — the panel usually updates automatically."*

**E13. 🔴 Save round-trip — stale views after Save. MUST FIX BEFORE PACKAGING.** Walkthrough surfaced two related bugs in the Save round-trip:

*Bug 1 — Speaker Panel reverts to stale snapshot.* After clicking *Save edits to DocAnalyser*, the panel header reverts to the pre-edit count (e.g. 304 paragraphs, 0 resolved, 304 unresolved) and the Paragraphs list reverts to showing `[SPEAKER_A]`/`[SPEAKER_B]` rather than the assigned names. The data is in fact saved correctly — clicking Refresh ¶ pulls the correct current state — but the user has no way of knowing this without trying Refresh ¶.

*Bug 2 — Source Document view in DocAnalyser does not auto-refresh.* After the user closes Word and looks at the Source Document view in DocAnalyser, the source pane still shows the pre-edit content (`[SPEAKER_A]`/`[SPEAKER_B]`). The work *is* saved — clicking *Edit in Word* re-opens the saved version with all changes — but the source pane doesn't reflect it. **A naive user will reasonably conclude the save failed.**

Both bugs share the same root cause: somewhere in the Save round-trip, a re-read from the canonical store is missing. After Save: the Speaker Panel should auto-refresh from the persisted state, and the Source Document view in DocAnalyser should auto-refresh from the database. Without this fix, a naive user is likely to: (a) repeat all their speaker assignments thinking the save failed; (b) re-open Word and re-save; (c) lose confidence in the round-trip and stop using the Word path entirely. This is the highest-impact UX bug surfaced by the walkthrough.

**Fix scope.** Conceptually simple (force re-read after Save), but the implementation likely needs to thread through the COM-Save-roundtrip code path, the Source Document view's data-binding, and any cached state in either view. Worth scoping properly during tomorrow's prioritisation session.

---

## F. Conceptual structure

**F1. 🟡 Five-category editing taxonomy.** The conceptual frame for all user-facing help about editing:

1. **Word-level edits** — fixing what was said. Mistranscriptions, typos. Two routes: local-only fix in the document, or *+ Correction…* button to promote to a Corrections List for future documents.
2. **Sentence structure edits** — where sentences end and new ones begin. Always document-local (no Corrections List equivalent). Affects precision of audio-linked summaries.
3. **Paragraph structure edits** — splits and merges. Sometimes needed when the heuristic agglomerates two speakers into one paragraph.
4. **Speaker assignment** — who's speaking in each paragraph. Three sub-actions: naming, per-paragraph assigning, bulk substitution.
5. **Free-form structural editing** — deleting passages, reordering, adding annotations. Normal Word editing; only constraint is preserving the timestamps (which item E6 addresses).

**The editing tasks are mechanically independent — the user can do them in any order.** The help layer should not prescribe a single "correct" sequence. Instead, present two sensible approaches that suit different working styles:

*Structure-first* (good for noisy or complex recordings): speakers → paragraphs → sentences → words. Diagnoses the shape of the document early; detail work happens against settled structure.

*Detail-first* (good for clean recordings with mostly-correct structure): words → paragraphs → speakers → sentences. Each step builds on cleaner text than the last.

Free-form structural editing (deleting passages, reorganising) typically goes last in either approach — investing detail work on text the user will remove is wasted effort.

This taxonomy is the spine of item E5 (the Word editing help doc) and of the help-icon copy in items C6 and E4.

---

## G. Inventory accuracy and naming

**G1. 🟢 Documentation cleanup — progressive transcription preview.** The progressive-display preview pane was removed but several documents still describe it as current behaviour: `Roadmap/Audio_Workflow_End_to_End_2026-04-28.md` Stage 2; `AUDIO_TRANSCRIPTION_GUIDE.md` step 3 of "A Typical Workflow"; `Documentation/ProjectMap/03_DOCUMENT_PROCESSING.md` `audio_handler.py` description; `Roadmap/Audio_Editing_Inventory_2026-05-01.md` §3 Stage 3. Consolidated documentation pass needed.

**G2. 🔵 v1.7-alpha state — confirm what's actually working end-to-end.** The cleanup dialog already shows the Corrections List dropdown; the Source Document already shows the Restore Backup button. Need to confirm whether the underlying logic is fully wired (apply-during-cleanup, *+ Correction…* round-trip, backups dialog functional) or whether these are scaffolding ahead of the underlying implementation. Affects the ship-now-vs-wait-for-v1.7-alpha packaging question.

**G3. 🔵 Naming — "Thread Viewer" vs "Source Document".** The inventory says "Thread Viewer", the actual UI says "Source Document". Decide which is canonical. "Source Document" is more accurate (the view is for working with the raw transcript, not for viewing AI conversation threads) but "Thread Viewer" persists in documentation. Decision tomorrow, then align everything.

---

## H. Routing buttons (only relevant when item A2 preference is not set)

**H1. 🟡 Help icons on the routing buttons.** A (?) icon next to *Thread Viewer* / *Source Document* and *Microsoft Word* buttons:

- Thread Viewer / Source Document — *"Edit and analyse the transcript inside DocAnalyser, with audio playback synchronised to each paragraph."*
- Microsoft Word — *"DocAnalyser will save the transcript as a Word document, then open it alongside an audio player and a speaker assignment panel. You'll be asked where to save the file."* The "you'll be asked where to save" is what removes the Save-dialog-surprise we identified during the walkthrough.

Becomes redundant when item A2 preference is set (no buttons to attach icons to).

---

## I. Implementation pattern notes

**I1. Help icon consistency.** Items C6, E4, and H1 all add help icons. Define the help-icon pattern once (icon style, popup behaviour, writing voice) and apply consistently. Otherwise three different in-context help mechanisms feel inconsistent.

**I2. Section B engine-awareness (item C5) introduces conditional logic in the cleanup dialog.** Not a problem — more honest, since cleanup options *should* depend on what the transcription gave you. Just noting it.

**I3. Hover tooltips are a pattern in their own right (added 3 May 2026).** Distinct from I1 (click-to-open help icons) and from the existing F1 contextual-help pattern. Hover tooltips appear automatically on mouse-over, auto-dismiss on move-away, and are best for very short hints (10–30 words). Used on non-obvious affordances such as the *"Double-click any row to seek the audio and play"* tooltip on the Speaker Panel paragraphs list (item E11). The full picture across all three patterns:

- **Hover tooltips** — auto-show on mouse-over; 10–30 words. For non-obvious affordances.
- **Click-to-open (?) icons** — visible icon, click for popup; 50–150 words. For longer explanations on naive-user surfaces (cleanup dialog, Speaker Panel).
- **F1 contextual help** — invisible until invoked; any length. The existing app-wide pattern via `context_help.py`. Retained as the power-user shortcut and for app-wide consistency.

When help-content authoring begins (Step 6 of the Implementation Strategy), the writer should classify each piece of help by length to choose the appropriate surface. All three patterns share the same underlying source so editing one entry updates all three surfaces.

---

## Decisions resolved 3 May 2026

The original *"Decisions to make tomorrow"* heading. All resolved with Ian in conversation with Claude. Full details in `Audio_Editing_Design_Decisions_Register_2026-05-02.md` §M and the companion Implementation Strategy.

1. **Item A2 sub-question — Hard preference.**
2. **Item C2 — Resolved.** Candidate A's wording as label; Candidate B's qualifier in help-icon copy.
3. **Item D1c — Defer to Tranche 4** (conditional on G2 confirming Backups are wired).
4. **Item G2 — In progress.** v1.7-alpha state confirmation is now Step 1.1 of the Implementation Strategy.
5. **Item G3 — Source Document canonical** for user-facing; code names unchanged.
6. **Packaging timing — Resolved.** v1.7-beta proceeds with Corrections Lists in scope; A3 + E10 (Track Changes for bulk edits) escalated from Tranche 3 to Tranche 2 to support the safety case for Corrections List apply. D1a (Apply Corrections List to existing document) also pulled into Tranche 2. Three new Tranche 2 steps (8a, 9a, 10a) added to the Implementation Strategy.

Additional decisions captured the same day, not in the original list:
- **Hard-or-soft sub-question for item A2** — Hard.
- **Track Changes per-action *just do it* opt-out** for Corrections Lists — deferred to Tranche 4 / future release.
- **Source Document path walkthrough timing** — folded into Step 1 of the Implementation Strategy as item 1.2.
- **Tranche scope** — four-tranche structure confirmed unchanged.
- **Help-icon interaction patterns** — captured here as new item I3 (above).

---

## What this list doesn't cover

We've not yet walked through:
- What happens when the user actually performs edits (word-level, sentence, paragraph) and clicks *Save edits to DocAnalyser* — i.e. the round-trip from Word back into DocAnalyser.
- The companion audio player window in detail.
- The Source Document / Thread Viewer editing path (we focused on Word).
- Stage 6 — AI processing on the cleaned transcript.

These remain to walk through in subsequent sessions.

---

*Captured by Claude during the walkthrough session, 2 May 2026. To be reviewed and worked into the formal roadmap and into specific design documents for the items that get scheduled.*
