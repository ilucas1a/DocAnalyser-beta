# Audio Editing — Design Decisions Register

**Date:** 2 May 2026
**Status:** Master checklist of design decisions arrived at across the audio-editing review and walkthrough sessions
**Companions:** `Roadmap/Audio_Editing_Inventory_2026-05-01.md`, `Roadmap/Audio_Editing_Walkthrough_Parking_Lot_2026-05-02.md`, `Roadmap/Audio_Editing_Implementation_Strategy_2026-05-02.md`
**Purpose:** Each decision is captured as a tickable line item so that at the end of implementation we can confirm every design intention found its way into the final product.

---

## How to use this document

Each decision below has a checkbox `[ ]`. As implementation progresses, tick decisions off `[x]` once verified to have landed correctly in the running app. The decisions are grouped by the same thematic sections used in the parking lot for cross-reference; the parking-lot item ID is given in parentheses for traceability.

A decision marked **[Decided]** has been settled in the conversation; it should be implemented as written.
A decision marked **[Decision pending]** still needs Ian's call before implementation begins.
A decision marked **[Conditional on …]** depends on a prior outcome (e.g., G2 investigation results).

---

## A. Earlier strategic decisions (pre-walkthrough)

### A.1 Local voice-based speaker identification — closed
- [ ] **[Decided]** Enhancement 25 (Local Voice-Based Speaker Identification) is closed as investigated-and-not-viable. AssemblyAI remains the production diarisation path. (Investigation log: `Voice_ID_Investigation_2026-05-01.md`.)
- [ ] **[Decided]** The roadmap status (`Documentation/ProjectMap/14_ROADMAP_STATUS.md`) is updated to reflect Enhancement 25's closure, with Map Integration renumbered to #26.
- [ ] **[Decided]** The headline enhancement count is corrected to 15 new enhancements (12–26), of which 8 original-list items are complete, 1 partial, and 2 outstanding.

### A.2 Faster-Whisper Large V3 vs Turbo
- [ ] **[Decided]** Faster-Whisper Large V3 remains the default transcription model. Turbo is offered as a faster opt-in option, but is not adopted as the default because of underperformance on at least some non-English audio (Vietnamese specifically tested).
- [ ] **[Decided]** Roadmap entry for Enhancement 24 reads: *"Added April 2026 as a local transcription option … Default-engine choice unresolved — Turbo underperforms Large V3 on at least some non-English audio (e.g. Vietnamese); Large V3 remains the safer default."*

### A.3 v3 AI Transcript Refinement spec
- [ ] **[Decided to defer]** v3 AI Transcript Refinement remains parked for this packaging cycle. May come off hold post-handover with the framing that AssemblyAI users have already accepted the cloud trade-off; AI refinement features inherit it cleanly.

### A.4 Cloud-AI text inference for speaker assignment
- [ ] **[Decided]** Cloud-AI text inference for speaker assignment is feasible and worth pursuing, but as part of v3 AI Refinement when v3 comes off hold. Not extracted as a standalone feature.
- [ ] **[Decided]** Local Ollama for speaker assignment is not pursued. Quality variance, output reliability, and context window constraints make it unlikely to beat the heuristic enough to justify the work.

---

## B. Settings and preferences

### B.1 Audio & Transcription Settings dialog (A1)
- [ ] **[Decided]** Compactness pass needed. API keys panel collapses into dropdowns or an expandable section so it doesn't dominate the dialog.

### B.2 Edit-in-Word-by-default preference (A2)
- [ ] **[Decided]** New preference *"When transcription completes, edit in Word"* in Audio & Transcription Settings.
- [ ] **[Decided]** When set: transcription completes → cleanup dialog opens automatically with the Source Document populated and visible behind it → user makes cleanup choices → on closing the dialog, routes directly to Word + companion player + speaker panel. No routing-buttons step.
- [ ] **[Decided]** When not set: current behaviour preserved (routing buttons after cleanup).
- [ ] **[Decided 3 May 2026]** **Hard preference.** User must change Audio Settings to override per-document. No escape hatch in the cleanup dialog — keeps the dialog uncluttered and respects that a user who has set the preference has decided. Mitigated by A1 (Settings dialog compactness pass) promoting the *Edit in Word by default* toggle to a prominent position in Settings so it's quick to flip when needed.

### B.3 Track Changes for bulk edits (A3 + E10)
- [ ] **[Decided]** New preference *"Show bulk edits as tracked changes for review"* in Audio & Transcription Settings, default on.
- [ ] **[Decided]** Affects: applying Corrections Lists, *Apply names to whole document*, future AI refinement actions, and the post-hoc *"Apply Corrections List to this document"* action.
- [ ] **[Decided]** When the preference is on, *Apply names to whole document* writes substitutions as Word tracked changes. User reviews per-paragraph using Word's native Accept/Reject UI.
- [ ] **[Decided]** Save-with-unresolved-changes behaviour: DocAnalyser refuses to save and prompts the user to resolve all tracked changes first. Wording: *"You have N unresolved tracked changes. Please accept or reject each one before saving."*
- [ ] **[Decided 3 May 2026 — Tranche 2 (locked)]** B.3 escalates to Tranche 2. Corrections Lists confirmed in v1.7-beta scope per Ian's call (PhD user has specifically requested the feature in correspondence). Track Changes is essential for the Corrections List apply path because word-level substitutions across a long document cannot be meaningfully previewed in a single dialog the way speaker-bulk can; they need native Word Accept/Reject in context. D1a (E.1) also pulled into Tranche 2 — see E.1 below.
- [ ] **[Decided 3 May 2026 — Tranche 4 / future]** Per-action *"just do it"* opt-out for Corrections List apply: an option to bypass Track Changes for experienced users who trust their Corrections List. Not for v1.7-beta; revisit after PhD user feedback.

---

## C. Documents Library and lifecycle

### C.1 In-progress entry during transcription (B1)
- [ ] **[Decided]** Add a Documents Library entry at the moment "Load" is clicked, with a *"Transcribing… (X% / elapsed time)"* status visible in the library tree.
- [ ] **[Decided]** Status updates mirror the existing main-window status line.
- [ ] **[Decided]** On completion: transitions to a normal document entry. On failure: transitions to an error state the user can re-trigger from.
- [ ] **[Decided]** Folder placement: probably the default folder unless configured otherwise (final design call when implementation begins).

---

## D. The cleanup dialog

### D.1 Top-of-dialog wording (C1)
- [ ] **[Decided]** Replace *"N segments transcribed. Choose options below."* with *"Your 1h 34m transcription is ready. Choose how to clean it up:"* (or equivalent — drops "segments", uses duration in user-meaningful units, gives a clear next-action verb).

### D.2 Listener back-channels rewording (C2)
- [ ] **[Decided 3 May 2026]** Checkbox label: *"Keep brief listener responses (mm-hmm, right) as [annotations]"* — Candidate A's wording, two examples not three (third example added visual weight without aiding comprehension).
- [ ] **[Decided 3 May 2026]** Help-icon copy on the checkbox: *"When someone says 'mm-hmm' or 'right' while another person is talking, DocAnalyser can fold those into the surrounding paragraph as bracketed annotations rather than removing them. Useful for preserving conversational rhythm in oral history interviews; usually unwanted in business or academic transcripts."* — Candidate B's qualifier captured in the help layer rather than the label, to keep the checkbox label compact while preserving the oral-history-specific framing.

### D.3 Skip rewording (C3)
- [ ] **[Decided]** Replace *"Skip — assign manually later"* with *"Skip — paragraphs will be created without speaker labels. You can assign speakers in Word or in DocAnalyser later."* (Or equivalent that explicitly tells the user that paragraphing still happens; only speaker labels are deferred.)

### D.4 Suggest speakers automatically rewording (C4)
- [ ] **[Decided]** Help-popup wording: *"Suggest speakers automatically — DocAnalyser will guess who's speaking based on patterns in the text (questions tend to come from the interviewer, longer answers from the interviewee). You should review the suggestions before relying on the result."* (Heuristic accuracy claim removed; honest review-before-relying advice retained.)

### D.5 Section B becomes engine-aware (C5)
- [ ] **[Decided pre-handover]** Remove *"Detect speakers by voice (not available — see Help for setup)"* radio entirely (C5-partial). The *"see Help for setup"* suffix actively misleads users.
- [ ] **[Decided post-handover]** Section B becomes fully engine-aware (C5-full):
  - [ ] **AssemblyAI with diarisation ticked** → no radio choice; Section B reads *"Speakers identified by AssemblyAI — assign names below"*; Section C is the naming step.
  - [ ] **AssemblyAI without diarisation, or any local engine** → two radios: Skip and Suggest speakers automatically.
  - [ ] **OpenAI Whisper cloud** → same as second case (no diarisation), two radios.

### D.6 Help icons throughout the cleanup dialog (C6)
- [ ] **[Decided]** A (?) icon next to each section heading and each radio option, opening a tooltip or popup with one or two plain-English sentences.
- [ ] **[Decided]** Specific targets: Section A heading, each Section A checkbox, Section B heading and each radio, Edit Lists button.
- [ ] **[Decided]** Edit Lists button help uses the Vietnam-veterans 30-interviews example as a concrete illustration of what a Corrections List does.

### D.7 Engineer-speak naming sweep (C7)
- [ ] **[Decided]** A wider sweep through the UI for engineer-leaking-into-UI terms beyond the cleanup dialog. Targets: "segments", "resolved/unresolved", "heuristic", "provisional", "back-channels", and any other similar terms surfaced during sweep.

---

## E. Post-hoc cleanup adjustments

### E.1 Apply Corrections List to existing document (D1a)
- [ ] **[Decided]** A *"Apply Corrections List to this document"* post-hoc action accessible from the Source Document view. Addresses the case where a Corrections List didn't exist when the document was first processed.
- [ ] **[Decided]** Respects the Track Changes preference (B.3 above).
- [ ] **[Decided 3 May 2026 — Tranche 2]** Pulled from Tranche 3 into Tranche 2 per Ian's call. Rationale: the typical oral-history use case (a series of related interviews) relies on being able to apply later-added Corrections List entries to documents processed earlier. Without D1a, Corrections Lists are a forward-only feature — much weaker. Slots into the Track Changes plumbing automatically since D1a's apply path goes through Track Changes review just like the cleanup-time apply does. Conditional only on G2 confirming/finishing the Corrections List wiring; the feature itself is in scope for v1.7-beta.

### E.2 Re-suggest speakers (D1b)
- [ ] **[Decided]** A *"Re-suggest speakers"* action that re-runs heuristic Phase 3 on existing paragraphs without rebuilding them. Tranche 3 priority.

### E.3 Reset to raw transcription (D1c)
- [ ] **[Decided 3 May 2026 — defer to Tranche 4]** Do not build *"Reset to raw transcription"* for v1.7-beta. Rationale: (a) the transcription cache in `audio_handler.py` makes "delete and re-import" effectively free in elapsed time when the same audio + engine + model + language are used; (b) `backups_manager.py` already provides granular point-in-time rollback (more useful than a full reset because it lets the user roll back to e.g. yesterday's state, not all the way to raw); (c) the only narrow case Reset uniquely solves is preserving a document's processed-output history across rollback, which is uncommon. Deferred conditional on G2 confirming Backups are wired; if G2 finds Backups scaffolded, revisit.

---

## F. Word editing view

### F.1 Welcome overlay on first Speaker Panel open (E1)
- [ ] **[Decided]** First-open modal explaining the three-window arrangement, the user's goal in this view, and where to start.
- [ ] **[Decided]** *Don't show again* tickbox.
- [ ] **[Decided]** Links to the Audio Transcription Guide (Pillar 1).

### F.2 Speaker Panel naming sweep (E2)
- [ ] **[Decided]** Replace *"304 paragraphs · 0 resolved · 304 unresolved"* with *"304 paragraphs · 0 named · 304 yet to be named"*.
- [ ] **[Decided]** *Prev unresolved* / *Next unresolved* buttons rename to *Prev unnamed* / *Next unnamed*.
- [ ] **[Decided to defer]** Three-state *verified* progress (*yet to be named* → *named (unverified)* → *verified*) deferred to post-handover release. Ship rename-only first.

### F.3 Speaker Panel light theme (E3)
- [ ] **[Decided]** Experiment with two or three light-background palette options when this work is reached. Current dark theme to be replaced.
- [ ] **[Decided]** Choice criterion: legibility, consistency with the rest of DocAnalyser's UI, accessibility.

### F.4 Help icons throughout the Speaker Panel (E4)
- [ ] **[Decided]** Help icon (?) next to each major control. Specific targets:
  - [ ] Named/yet-to-be-named stats line
  - [ ] Audio block (double-click to seek)
  - [ ] Speaker names block
  - [ ] *+ Add speaker*
  - [ ] *Assign* vs *Apply names to whole document*
  - [ ] *Prev unnamed* / *Next unnamed*
  - [ ] *Refresh ¶*
  - [ ] *Correction…*
  - [ ] *Whole doc / This ¶* timestamp toggles
  - [ ] *Show all / Hide secondary / Hide all* timestamp visibility
  - [ ] *Save edits to DocAnalyser* (with explicit note that closing Word without it loses work)
- [ ] **[Decided]** *Refresh ¶* help-copy reflects that the panel usually updates automatically: *"Re-sync the panel with Word if you notice a mismatch — the panel usually updates automatically."*

### F.5 "Editing transcripts in Word" help document (E5)
- [ ] **[Decided]** Short help-menu entry covering the editing taxonomy with examples (F1 from parking lot), the dependencies between editing categories in suggested order, and the Word path's hidden constraints.
- [ ] **[Decided]** Two screens of plain prose. Linked from the welcome overlay.

### F.6 Timestamp content controls (E6)
- [ ] **[Decided]** `[MM:SS]` paragraph headers rendered as Word content controls marked "cannot be deleted, cannot be edited."
- [ ] **[Decided]** Secondary `{MM:SS}` sentence-level markers within paragraphs given the same treatment.
- [ ] **[Decided]** Splits and merges still work because they operate on paragraph boundaries, not timestamp content.
- [ ] **[Fallback]** If content controls don't behave as required in Compatibility Mode, fall back to Word document protection (read-only sections containing the timestamps).

### F.7 Split rule and confirmation dialog (E7)
- [ ] **[Decided]** **Split rule:** the sentence containing the cursor always becomes the first sentence of the new paragraph. Pressing Enter anywhere within a sentence (start, middle, end) produces the same result. One rule, no sub-cases.
- [ ] **[Decided]** Split confirmation dialog: *"Do you wish to create a new paragraph? The new paragraph will start with the sentence beginning '…first few words…' at [MM:SS]."* Yes / No / *Don't show again for splits*.
- [ ] **[Decided]** New paragraph inherits the originating paragraph's speaker assignment by default.
- [ ] **[Decided]** Sentence-boundary detection handles edge cases (abbreviations, multiple punctuation, sentence-final ellipses, embedded `?` mid-sentence).
- [ ] **[Fallback]** If sentence-boundary detection accuracy is poor, fall back to a rule that asks the user to confirm where the split should go in ambiguous cases.

### F.8 Merge confirmation dialog (E7)
- [ ] **[Decided]** Merge confirmation dialog: *"This will merge the two paragraphs. The merged paragraph will keep the speaker assigned to the paragraph above. Do you wish to continue?"* Yes / No / *Don't show again for merges*.
- [ ] **[Decided]** Separate *Don't show again* flags for splits vs merges (so users can dismiss the lower-value one while keeping the higher-value one).

### F.9 Footer message wording (E8)
- [ ] **[Decided]** Replace *"Assigned 'Tony' to para N"* with friendlier wording — *"first paragraph"* or echo the visible `[MM:SS]` timestamp.
- [ ] **[Decided]** Confirm message persistence behaviour is right (visible long enough to see; not so long it's noise).

### F.10 Assign vs Apply names to whole document — clarification (E9)
- [ ] **[Decided]** Help-icon copy explains when to use each: per-paragraph for cases where the heuristic mis-labelled some paragraphs (so bulk substitution would propagate the error) or where the user wants to verify before committing; bulk for cases where labels are correct and only names need substituting.
- [ ] **[Decided]** Single-click on a Paragraphs list row navigates the Word cursor and seeks audio (and plays) — confirmed behaviour during walkthrough.

### F.11 Apply names to whole document with Track Changes (E10)
- [ ] **[Decided]** When the Track Changes preference is on, *Apply names to whole document* writes substitutions as tracked changes. The user reviews per-paragraph using Word's native UI. Subsumes the need for a separate "undo bulk apply" mechanism.

### F.11a Speaker-bulk confirmation dialog (added 3 May 2026)
- [ ] **[Decided 3 May 2026 — Tranche 2, independent of Track Changes scope]** Before *Apply names to whole document* commits, show a confirmation dialog that summarises the substitution and reminds the user that the heuristic's assignments are suggestions only.
- [ ] **[Decided]** Seed wording: *"This will replace [SPEAKER_A] → Tony and [SPEAKER_B] → Chris in all 304 paragraphs. The heuristic's speaker assignments are suggestions only — paragraphs where the heuristic guessed wrong will get the wrong name. You can fix individual paragraphs afterwards using the Speaker Panel. Apply now? Yes / No"*
- [ ] **[Decided]** Independent of F.11 (Track Changes). The dialog covers the speaker-bulk operation specifically and is *not* a substitute for Track Changes on Corrections Lists application — Corrections Lists span many small word-level substitutions that cannot be meaningfully summarised in one dialog.

### F.12 Paragraphs list double-click discoverability (E11)
- [ ] **[Decided]** Add an on-hover tooltip on the Paragraphs list area: *"Double-click any row to seek the audio and play."*
- [ ] **[Decided]** Lighter Speaker Panel theme (F.3 above) will naturally make the existing parenthetical instruction more visible.

### F.13 Refresh ¶ confirmed as rare-edge-case only (E12)
- [ ] **[Confirmed]** Speaker Panel auto-updates after splits via COM polling. Refresh ¶ needed only in edge cases (rapid edits, clipboard operations, async issues).

### F.14 Save round-trip auto-refresh (E13) — HIGHEST PRIORITY
- [ ] **[Decided]** After *Save edits to DocAnalyser*, the Speaker Panel auto-refreshes from the persisted state (no manual Refresh ¶ needed).
- [ ] **[Decided]** After *Save edits to DocAnalyser*, the Source Document view in DocAnalyser auto-refreshes from the database.
- [ ] **[Decided]** Both fixes are pre-handover blockers. A naive user must not be able to mistake a successful save for a failed one.

---

## G. Conceptual structure

### G.1 Five-category editing taxonomy (F1)
- [ ] **[Decided]** Five categories used as the spine of all user-facing help about editing:
  1. Word-level edits (mistranscriptions, typos)
  2. Sentence structure edits (where sentences end)
  3. Paragraph structure edits (splits and merges)
  4. Speaker assignment (who's speaking)
  5. Free-form structural editing (deleting, reordering, annotations)
- [ ] **[Decided]** The taxonomy is locked before help-content authoring begins.
- [ ] **[Decided]** Two recommended editing orders presented in the Guide:
  - Structure-first: speakers → paragraphs → sentences → words (good for noisy/complex recordings)
  - Detail-first: words → paragraphs → speakers → sentences (good for clean recordings with mostly-correct structure)
- [ ] **[Decided]** Free-form structural editing typically goes last in either approach.
- [ ] **[Decided]** The order is *suggested* in the help layer, not enforced. Tasks are mechanically independent.

---

## H. Two pillars of comprehension

### H.1 Pillar 1 — Audio Transcription Guide
- [ ] **[Decided]** A single readable document covering the end-to-end workflow narratively. ~6–10 screens of plain prose.
- [ ] **[Decided]** Replaces or substantially rewrites the current `AUDIO_TRANSCRIPTION_GUIDE.md` (which has stale references — local voice-ID, progressive preview pane, etc).
- [ ] **[Decided]** Lives in the Help menu and is linked from the welcome overlay.

### H.2 Pillar 2 — Dense in-context help
- [ ] **[Decided]** Help icons on every meaningful control across the cleanup dialog, Speaker Panel, and routing buttons.
- [ ] **[Decided]** Tooltips on non-obvious affordances (e.g., double-click on Paragraphs list).
- [ ] **[Decided]** Plain-English wording in every dialog.

### H.3 Single-author content principle
- [ ] **[Decided]** Guide and help-icon copy authored as one piece of writing by one person in one pass for voice consistency.
- [ ] **[Decided]** Five-category taxonomy is the spine; help-icon copy is the leaf-level expression; Guide weaves the leaves into a narrative.

---

## I. Routing buttons

### I.1 Help icons on routing buttons (H1)
- [ ] **[Decided]** Help icon (?) next to *Thread Viewer / Source Document* and *Microsoft Word* buttons.
- [ ] **[Decided]** Microsoft Word help text flags both that a Save dialog will appear and that three windows will open together (Word + companion player + speaker panel).
- [ ] **[Decided]** Becomes redundant when the Edit-in-Word-by-default preference (B.2) is set.

---

## J. Implementation patterns

### J.1 Help-icon implementation pattern (I1)
- [ ] **[Decided]** Help-icon pattern designed once (icon style, popup behaviour, writing voice) and applied uniformly across cleanup dialog, Speaker Panel, and routing buttons. Avoids inconsistency between three different in-context help mechanisms.
- [ ] **[Decided 3 May 2026]** Three help-interaction patterns coexist in the app, each with a clear role:
  1. **Hover tooltips** — appear automatically on mouse-over, auto-dismiss on move-away. For very short hints (10–30 words). Best on non-obvious affordances such as the *"Double-click any row to seek the audio and play"* tooltip on the Speaker Panel paragraphs list (F.12 / item E11 in the parking lot).
  2. **Click-to-open (?) help icons** — visible icon next to a control; click opens a popup that stays open until dismissed. For longer explanations (50–150 words). The naive-user-friendly pattern. Used on the cleanup dialog (D.6 / C6), Speaker Panel (F.4 / E4), and routing buttons (I.1 / H1).
  3. **F1 contextual help** — existing app-wide pattern via `context_help.py`. User hovers over a widget and presses F1; popup appears. Invisible until invoked. Retained as the power-user shortcut and for consistency with the rest of DocAnalyser.
- [ ] **[Decided 3 May 2026]** All three patterns share the same underlying help-text source (`help_texts.json` today, eventually the SQLite-backed message store when Enhancement 15 lands). Edit one entry, all three surfaces update. No content drift between F1 help and the new (?) help.

### J.2 Section B engine-awareness (I2)
- [ ] **[Decided]** Cleanup dialog is permitted to be engine-aware. Cleanup options *should* depend on what the transcription gave you. Conditional logic in the dialog code is acceptable.

---

## K. Inventory accuracy and naming

### K.1 Documentation cleanup — progressive transcription preview (G1)
- [ ] **[Decided]** Consolidated documentation pass needed. Remove or revise references to the removed progressive-display preview pane in:
  - [ ] `Roadmap/Audio_Workflow_End_to_End_2026-04-28.md` Stage 2
  - [ ] `AUDIO_TRANSCRIPTION_GUIDE.md` step 3 of "A Typical Workflow" (will be subsumed by the new Guide rewrite)
  - [ ] `Documentation/ProjectMap/03_DOCUMENT_PROCESSING.md` `audio_handler.py` description
  - [ ] `Roadmap/Audio_Editing_Inventory_2026-05-01.md` §3 Stage 3

### K.2 v1.7-alpha state confirmation (G2)
- [ ] **[Pending]** Confirm what is actually working end-to-end:
  - [ ] Corrections List dropdown wired vs scaffolded
  - [ ] *+ Correction…* round-trip functional
  - [ ] Restore Backup functional
- [ ] **[Pending]** Outcome determines packaging strategy and feeds into D1a (E.1 above).

### K.3 Thread Viewer vs Source Document naming (G3)
- [ ] **[Decided 3 May 2026]** **Source Document** is the canonical user-facing term. Used in UI, help-icon copy, the Audio Transcription Guide, the welcome overlay, the routing button label, and any other user-visible text.
- [ ] **[Decided 3 May 2026]** Internal code names unchanged — `thread_viewer.py`, `ThreadViewerWindow`, `viewer_thread.py`, `_show_thread_viewer()`, etc all keep their current names. Renaming would touch dozens of import statements for cosmetic value to readers of code.
- [ ] **[Decided 3 May 2026]** Documentation convention: Project Map sections continue to reference the code module by its code name in headings (e.g. *thread_viewer.py* as a section heading); body prose uses the user-facing name (*Source Document window*). Audio Editing Inventory and the new Audio Transcription Guide default to *Source Document* throughout.
- [ ] **[Decided 3 May 2026]** When in conversation mode, the Source Document window's title or header may switch to *"Conversation"* or similar — a window changing its label by mode is normal Tkinter UI.

---

## L. Process and verification

### L.1 Per-step verification discipline
- [ ] **[Decided]** Every implementation step has: (a) implementation acceptance, (b) targeted scenario tests written before implementation, (c) sign-off walkthrough by Ian.
- [ ] **[Decided]** High-risk items (E13, E6) additionally have (d) regression spot-check.
- [ ] **[Decided]** No step starts before the previous step has signed off.

### L.2 Tranche sign-off gates
- [ ] **[Decided]** Tranche 1 sign-off gate: consolidated walkthrough repeating the full audio-to-Word-to-Save sequence end-to-end, covering all bug fixes together.
- [ ] **[Decided]** Tranche 2 sign-off gate: consolidated naive-user pass running the full audio-to-edited-transcript workflow as if Ian were a first-time user.

### L.3 Packaging strategy
- [ ] **[Decided]** Build packaged as **DocAnalyser v1.7-beta** for the PhD user, not v1.7 release. Acknowledges Source Document path, Stage 6, and Tranche 3 items remain to be addressed.
- [ ] **[Decided]** Welcome-to-beta note in the Help menu listing what's known to be rough.
- [ ] **[Decided]** After PhD user feedback (~2–3 weeks), v1.7 (no beta tag) ships with Tranche 3 items.

---

## M. Decisions resolved 3 May 2026

This section was *"Decisions still open at end of conversation"* during the 2 May session. All eight items below were resolved with Ian on 3 May 2026 in conversation with Claude. The resolutions are reflected in the relevant sections above; the items are listed here as a brief audit trail. Some retain `[ ]` because they describe intentions that have not yet landed in the running app — a `[x]` requires verification on the running app per the convention in the *How to use this document* section at the top.

1. [ ] **B.2 sub-question — Resolved.** Hard preference. See B.2 above.
2. [ ] **D.2 (C2) — Resolved.** Candidate A's wording as the checkbox label; Candidate B's qualifier captured in help-icon copy. See D.2 above.
3. [ ] **E.3 (D1c) — Resolved.** Defer to Tranche 4 / future release; conditional on G2 confirming Backups are wired. See E.3 above.
4. **K.2 (G2) — In progress.** v1.7-alpha state confirmation is now Step 1.1 of the Implementation Strategy. Not a decision but an investigation; outcome shapes Tranche 1 sizing rather than v1.7-beta scope (Corrections Lists are confirmed in scope per item 6 below regardless of G2 outcome).
5. [ ] **K.3 (G3) — Resolved.** *Source Document* canonical for user-facing; code names unchanged. See K.3 above.
6. [ ] **B.3 (A3 + E10) priority — Resolved.** Track Changes escalates to **Tranche 2 (locked)**. Corrections Lists confirmed in v1.7-beta scope per Ian's call. D1a (E.1) also pulled into Tranche 2. See B.3 and E.1 above. New item F.11a (speaker-bulk confirmation dialog, Tranche 2) added independent of Track Changes scope.
7. **Source Document path walkthrough — Resolved.** Option C: folded into Step 1 as item 1.2 (between G2 investigation and F1 taxonomy lock). Step 1 grows from half-a-day to roughly 2–3 days of investigation work. See `Audio_Editing_Implementation_Strategy_2026-05-02.md` §5 Step 1.
8. **Tranche scope confirmation — Resolved.** Four-tranche structure unchanged. Tranche 2 grows in scope (A3 + E10 Track Changes ~4–5 days, D1a 2 days, F.11a half-day) but no items move between tranches. Combined Tranche 1+2 build estimate ~18–20 days, ~3–4 calendar weeks plus per-step verification.

---

## Summary of decisions captured 3 May 2026

For traceability, the eight Section M resolutions touched the following items elsewhere in this register:
- **B.2** — hard-preference sub-bullet updated.
- **B.3** — Tranche 2 lock; new sub-bullet for the per-action opt-out (Tranche 4 / future).
- **D.2** — wording resolved.
- **E.1 (D1a)** — pulled from Tranche 3 into Tranche 2.
- **E.3 (D1c)** — deferred to Tranche 4.
- **F.11a (new item)** — speaker-bulk confirmation dialog, Tranche 2.
- **J.1** — three-help-patterns sub-bullets added.
- **K.3** — Source Document canonical resolved.

Also captured during the same conversation but reflected in the companion documents:
- **Implementation Strategy §5 Step 1** — expanded from half-a-day to 2–3 days (sub-steps 1.1 G2, 1.2 Source Document walkthrough, 1.3 F1 taxonomy lock).
- **Implementation Strategy §5** — three new Tranche 2 steps (8a, 9a, 10a) inserted for F.11a, A3+E10, and D1a respectively.
- **Implementation Strategy §4** — Tranche 2 totals revised; Tranche 3 reduced (A3+E10 and D1a moved out).
- **Parking Lot §I** — new I.3 item added naming hover tooltips as a distinct pattern from I1 (click-to-open icons) and the F1 mechanism.

---

## How decisions feed into final verification

At the end of implementation, every checkbox above should be tickable. The flow:

1. Each Tranche-1 and Tranche-2 implementation step verifies the specific decisions assigned to it (via the targeted scenario tests in the strategy document).
2. Tickable items are marked `[x]` once verified.
3. The Tranche 1 and Tranche 2 sign-off gates confirm all decisions in those tranches have landed.
4. Before packaging as v1.7-beta, this register is reviewed end-to-end. Any unticked items are either: addressed before handover, explicitly accepted as Tranche 3 deferrals, or flagged as rough edges in the welcome-to-beta note.

This register is the answer to the question *"did all our design decisions find their way into the final product?"* — by being a checklist that has to be walked through at the end.

---

*Compiled by Claude on 2 May 2026 from the audio-editing review and walkthrough sessions.*
