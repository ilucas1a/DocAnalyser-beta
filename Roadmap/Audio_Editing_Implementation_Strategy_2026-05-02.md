# Audio Editing — Implementation Sequence and Strategy

**Date:** 2 May 2026
**Status:** Draft for Ian's review before implementation begins
**Companion to:** `Roadmap/Audio_Editing_Walkthrough_Parking_Lot_2026-05-02.md`
**Goal:** Get a workable version of DocAnalyser into your PhD user's hands as soon as that can be done thoroughly, with each change verified to have landed effectively before the next change is started.

---

## 1. The shape of the problem

The walkthrough produced 26 parking-lot items spanning settings, the cleanup dialog, the Word editing view, the Source Document view, and various documentation cleanups. Some are bugs that must be fixed before anyone unfamiliar with DocAnalyser sees it; some are polish items that improve the experience but don't gate the handover; some are deferred features that genuinely belong in the next release rather than this one.

The strategy below sorts those 26 items into four release tranches, proposes a sequence within each, and defines the verification pattern that every step passes through before the next step begins.

The fundamental principle: **a naive user must be able to complete an audio-to-edited-transcript workflow on their first try without losing trust in the tool.** Anything that breaks that trust in the first session is a packaging blocker. Anything that merely adds friction or imperfect polish is not.

---

## 2. The two pillars of comprehension

A late addition to the parking lot, but a structurally important one: **comprehension support has two pillars, both essential, neither sufficient alone.**

**Pillar 1 — A single readable Audio Transcription Guide.** A document the user can read end-to-end before they start, or refer back to when they're stuck. Linear, narrative, the whole workflow described as a story rather than as a reference manual. Lives in the Help menu and is linked from the welcome overlay.

**Pillar 2 — Dense in-context help throughout the workflow.** Help icons on every meaningful control, tooltips on every non-obvious affordance, plain-English wording in every dialog. Caught at the point of use, where the user actually needs it.

The two pillars work together: a user who reads the Guide first has the mental model and uses the in-context help as confirmation; a user who plunges in without reading uses the in-context help to learn as they go and reaches for the Guide when something needs deeper context. Both kinds of user are supported.

The key implication for sequencing: **the Guide and the in-context help are the same content authored once and surfaced twice.** The five-category editing taxonomy (F1) is the spine; the help-icon copy (C6, E4, H1) is the leaf-level expression; the Guide weaves the leaves into a narrative. Authoring them separately would produce inconsistencies and triple the work; authoring the spine once and deriving both surfaces from it is the discipline that makes this affordable.

This means the help-content work is one piece of writing, not two — and it should be done by one person in one pass for consistency of voice. It also means the Guide is **Tranche 2 work**, not a deferred polish item, because without it the in-context help has no grounding and a user who wants the full picture has nowhere to go.

---

## 3. Verification — the principle that gates every step

**Every implementation step has a defined verification gate that must pass before the next step starts.** No step is considered complete until it has been demonstrated to work as intended on the running app, against the specific scenarios the change was meant to address. This is not a final QA pass; it is a per-step discipline.

The reason this matters: changes to a non-trivial codebase tend to interact in unexpected ways. The Save round-trip touches code paths used by other workflows; content controls in Word have edge cases; help-icon plumbing modifies UI containers used by many dialogs. A bug introduced today and discovered three days later requires unstacking three days of subsequent work to diagnose. A bug caught the same day it's introduced is a 30-minute fix.

Each item below is therefore presented as a triple: **what we change, how we verify it, and what we accept as the test passing.** The verification step is the responsibility of whoever made the change. If verification fails, the next step does not begin until the failure is understood and either fixed or explicitly deferred.

### The verification pattern

For every item in Tranches 1 and 2, three components:

**(a) Implementation acceptance.** The narrowest form of "done" — the code compiles, the change is in place, no obvious regressions in basic startup and load.

**(b) Targeted scenario tests.** A small number of specific things the user must be able to do (or be prevented from doing). These are written *before* implementation starts so we know what we're aiming at, not retrofitted afterward to match what we built.

**(c) Sign-off walkthrough.** A short hands-on session — five or ten minutes for most items — where Ian (or whoever is closest to the user perspective) actually performs the scenarios on the running app. Only after sign-off does the next item begin.

For a few items (notably E13 and E6, which touch core workflows) a fourth component is added:

**(d) Regression spot-check.** Re-run the audio-to-Word-to-Save round-trip from the walkthrough to confirm previously-working behaviour still works. Catches inadvertent breakage of adjacent code paths.

The verification gates are explicit in §5 below.

---

## 4. The four tranches

### Tranche 1 — Pre-handover blockers
*Must ship before the PhD user sees the build. These are items where a naive user will lose trust within their first session.*

The three highest-priority items from the walkthrough plus the v1.7-alpha state confirmation:

- **G2 — Confirm v1.7-alpha state.** Before anything else, we need to know whether the Corrections List dropdown in the cleanup dialog is wired or scaffolded, whether *+ Correction…* round-trips, whether Restore Backup is functional. *Estimate: half-day investigation.* This determines what's already in the build vs what needs building.
- **E13 — Save round-trip stale views.** After Save, both the Speaker Panel and the Source Document view must auto-refresh from the canonical store. **The single most important fix because it makes successful saves *appear* as failures.** *Estimate: 1–2 days, scoping-dependent.*
- **E6 — Timestamp content controls.** `[MM:SS]` and `{MM:SS}` markers rendered as Word content controls that cannot be deleted or edited. *Estimate: 1–2 days; some risk that Word's content control API has edge cases (compatibility mode, particular Word versions) that need testing.*
- **C5 partial — Remove the misleading voice-detection radio.** Engine-aware Section B is more work; for the handover, removing the *"Detect speakers by voice (not available — see Help for setup)"* radio entirely is sufficient. The wording is actively misleading; removal eliminates the false promise without requiring the full engine-aware redesign yet. *Estimate: a couple of hours.*

**Tranche 1 total: ~5 days of work, with G2 first to bound the rest.**

### Tranche 2 — Comprehension and onboarding
*Ships before the PhD user. The walkthrough exposed that mechanically the system works; what's missing is the layer that helps a user understand what they're seeing.*

Two parts: the help content itself (authored once, surfaced twice), and the Word view onboarding mechanics:

**Part A — The help content (authored as one piece):**
- **F1 — Editing taxonomy locked down.** The five-category structure as the spine of all help content. Reviewed and finalised before any writing starts. *Estimate: half-day discussion.*
- **NEW — Audio Transcription Guide.** Single readable document covering the end-to-end workflow narratively. Lives in the Help menu. ~6–10 screens of plain prose. Replaces or substantially rewrites the current `AUDIO_TRANSCRIPTION_GUIDE.md` (which has stale references to features that won't ship — local voice-ID, the progressive preview pane, etc). *Estimate: 2 days.*
- **C1, C2, C3, C4 — Cleanup dialog wording and help.** Top-of-dialog wording, listener back-channels, Skip rewording, Suggest-speakers help-popup. *Estimate: 1 day.*
- **C6 + E4 + H1 — Help icons throughout.** Pattern designed once (I1) and applied to the cleanup dialog, the Speaker Panel, and the routing buttons. The bulk of the in-context help work. *Estimate: 3 days for the full sweep including writing the copy, with the copy drawing directly from the Guide.*
- **E2 — Speaker Panel resolved/unresolved → named/yet-to-be-named rename.** Recommendation: ship *without* the *verified* state for the PhD user (just rename); revisit the verified state in the next release. *Estimate: half-day.*

**Part B — Word view onboarding mechanics:**
- **E1 — Welcome overlay on first open of the Speaker Panel.** Modal explaining the three-window arrangement, the user's goal, where to start. *Don't show again* tickbox. Links to the Guide. *Estimate: 1 day.*
- **E7 — Split/merge confirmation dialogs with the cursor-sentence rule.** *Estimate: 2–3 days; the dialog is straightforward but the sentence-boundary detection logic needs care to handle edge cases (sentence ending with abbreviation, multiple punctuation, etc).*

**Tranche 2 total (revised 3 May 2026): ~13–15 days**, expanded to include Corrections Lists supporting work per Ian's call. Three additional steps inserted into §5 below — Steps 8a (speaker-bulk confirmation dialog), 9a (Track Changes infrastructure), and 10a (D1a apply Corrections List to existing document).

**Combined Tranche 1+2 (revised): ~18–20 days, ~3–4 calendar weeks of build time, plus per-step verification.**

### Tranche 3 — Important but deferrable to next release
*The PhD user can use the build without these. Each adds value; absence does not block the handover.*

Polish, deeper features, and items that improve experienced-user velocity but don't gate naive-user comprehension:

- **A1 — Audio & Transcription Settings compactness pass.** *Estimate: 1 day.*
- **A2 — *Edit in Word by default* preference.** *Estimate: 2 days.*
- **B1 — Documents Library in-progress entry.** *Estimate: 1–2 days.*
- **C5 full — Engine-aware Section B.** AssemblyAI-with-diarisation case. Needs engine-detection plumbing. *Estimate: 1–2 days.*
- **C7 — Engineer-speak naming sweep across the rest of the UI.** *Estimate: 1–2 days; mostly hunting through code.*
- **E3 — Speaker Panel light theme.** *Estimate: 1 day for the experiment, 1 day for chosen palette.*
- **E8, E9, E11 — Speaker Panel small wording and discoverability fixes.** *Estimate: 1 day collectively.*

*Note (3 May 2026): A3 + E10 (Track Changes for bulk edits) and D1a (Apply Corrections List to existing document) were pulled out of Tranche 3 into Tranche 2 per Ian's call to bring Corrections Lists into v1.7-beta scope. See §5 Steps 9a and 10a below.*

**Tranche 3 total (revised 3 May 2026): ~2 weeks of work spread across smaller items.**

### Tranche 4 — Deferred to a later release or pending decision

- **A2 sub-question** — hard vs soft Edit-in-Word preference. Decide tomorrow.
- **D1b, D1c** — *Re-suggest speakers* and *Reset to raw transcription* post-hoc actions. Lower-frequency cases.
- **E2 *verified* state** — three-state speaker-naming progress (yet-to-be-named / named / verified). Real value but adds tracking machinery; revisit after the PhD user has used the rename-only version.
- **G1 — Documentation cleanup pass** for stale progressive-preview references. Pure tidiness; do when convenient.
- **G3 — *Thread Viewer* vs *Source Document* naming.** Decide tomorrow which is canonical, then align documentation. Low-frequency cosmetic.

---

## 5. The sequence within Tranches 1 and 2 — with verification gates

The actual order of work matters because some items unblock or simplify others. Each step includes its targeted scenario tests and what counts as sign-off before moving on.

### Step 1 — G2 v1.7-alpha investigation + Source Document walkthrough + F1 taxonomy lock

*Revised 3 May 2026. No code changes; investigation, walkthrough, and conversation only.*

**Three sub-steps:**

**1.1 — G2 v1.7-alpha investigation.** Code-reading exercise. Read through the Corrections List wiring, the *+ Correction…* round-trip, and the Restore Backup machinery in the running codebase. Produce a written statement of which features are live, partly wired, or scaffolded — and what additional Tranche 1 work (if any) is needed to finish them. Per the 3 May call, Corrections Lists are committed to v1.7-beta scope, so any scaffolding becomes Tranche 1 work to complete; the feature itself is not optional.

**1.2 — Source Document walkthrough.** Walk-through session of the Source Document path (in-app Tkinter editor — formerly called Thread Viewer; now canonically *Source Document* per Decisions Register K.3). Same kind of session as the 2 May walkthrough did for the Word path. Capture findings into the parking lot. Anything found that's a pre-handover blocker may add to Tranche 1; lower-priority items go to Tranche 3.

**1.3 — F1 taxonomy lock.** Confirm the five-category editing taxonomy. Spine of all help content authored in Step 6.

**Targeted scenario tests (1.1 only — 1.2 is exploratory; 1.3 is conversation).**
1. *Corrections List dropdown:* select a list, run cleanup on a fresh transcription, verify the corrections were applied (or that they were not, if the feature is scaffolded only).
2. *+ Correction… button:* click the button, attempt to add a correction, verify the round-trip into the Corrections List storage.
3. *Restore Backup:* trigger a backup snapshot, modify the document, restore from snapshot, verify the restore actually rolled the document back.

**Sign-off.** Ian reviews the 1.1 written statement, the 1.2 walkthrough findings, and confirms the 1.3 taxonomy. Outputs feed into Tranche 1 sizing (1.1), Tranche 1 scope additions if any (1.2), and the help-content sprint (1.3).

*Estimated time: 2–3 days for the full Step 1.*

### Step 2 — E13 scoping pass

*No code changes yet; reading the code path for the Save round-trip to determine fix scope.*

**What we change.** Nothing in the codebase. We produce a clear understanding of where the post-Save refresh needs to be added — in two specific places, in a data-binding rework, or somewhere in between — and a revised time estimate for the actual fix.

**Targeted scenario tests.** None at this step (no behaviour change). The output is a written scoping note attached to the parking lot E13 entry.

**Sign-off.** Ian reviews the scoping note. If it's the simple version (refresh calls in two places), Step 4 below is half a day. If it's the data-binding rework, Step 4 is several days, and we may want to consider whether the partial fix (just the Source Document view auto-refresh, leaving the panel manual) is sufficient for the PhD user.

*Estimated time: 1–3 hours.*

### Step 3 — C5-partial: remove the misleading voice-detection radio

*Smallest item in Tranche 1; good for warming up the testing discipline.*

**What we change.** Remove the *"Detect speakers by voice (not available — see Help for setup)"* radio from the cleanup dialog Section B entirely. Section B becomes two radios: Skip and Suggest speakers automatically.

**Targeted scenario tests.**
1. Open the cleanup dialog. Confirm the third radio is no longer present.
2. Skip and Suggest-speakers radios still function as before.
3. Run cleanup with each remaining option; verify the heuristic Skip and Suggest paths produce the same output as previously.
4. Verify no other dialog or settings dialog references the removed radio (search the codebase for any hooks).

**Sign-off.** Ian opens the cleanup dialog on a fresh transcription, confirms the third radio is gone, runs cleanup with each remaining option, and confirms the source pane content is correct.

*Estimated time: 2–3 hours including verification.*

### Step 4 — E13: Save round-trip stale views

*The single highest-impact bug fix.*

**What we change.** After *Save edits to DocAnalyser* completes, both the Speaker Panel and the Source Document view re-read from the canonical store and refresh their displays. Implementation depends on Step 2 scoping outcome.

**Targeted scenario tests.**
1. Open Word from a fresh transcription. Assign Tony to SPEAKER_A and Chris to SPEAKER_B. Apply names to whole document. Click Save edits to DocAnalyser. *Speaker Panel should now show 305 (or whatever) named paragraphs, [Tony] / [Chris] in the list, no manual Refresh ¶ needed.*
2. Close Word (saving when prompted). Look at the Source Document view in DocAnalyser. *Source pane should now show [Tony] and [Chris] in paragraph headers, not [SPEAKER_A] and [SPEAKER_B].*
3. Repeat with a paragraph split: split a paragraph in Word, save, close. Verify both views show 305 (or whatever) paragraphs after save.
4. *Regression spot-check:* re-run the basic transcription-to-cleanup-to-Word workflow end-to-end on a fresh audio file. Confirm no new failures introduced.

**Sign-off.** Ian performs the full walkthrough scenario from yesterday's session and confirms that the post-Save state in both the Speaker Panel and Source Document view matches what's actually been saved.

*Estimated time: half a day to several days, depending on Step 2 outcome.*

### Step 5 — E6: timestamp content controls

*Highest-priority data-integrity protection.*

**What we change.** `[MM:SS]` paragraph headers and `{MM:SS}` sentence-level markers rendered as Word content controls with deletion and editing disabled.

**Targeted scenario tests.**
1. Open Word from a fresh transcription. Try to select a `[MM:SS]` token and press Delete. *Nothing should happen; the timestamp remains.*
2. Try to position the cursor inside the `[MM:SS]` text and type a character. *Typing should be blocked.*
3. Try the same with a secondary `{MM:SS}` marker. *Same behaviour.*
4. Confirm splits still work: place cursor in a paragraph, press Enter. *The split should proceed normally; the new paragraph's `[MM:SS]` should be intact.*
5. Confirm merges still work: delete a paragraph break. *The merge proceeds; the surviving `[MM:SS]` is intact.*
6. Save the document, close Word, re-open. *Content controls survive the save round-trip; deletion is still blocked on re-open.*
7. *Regression spot-check:* the full transcription-to-edit-to-Save round-trip works without error.

**Sign-off.** Ian repeats the timestamp-deletion experiment from yesterday and confirms it now fails (in a good way) on every kind of timestamp.

**Risk and fallback.** Word's content control API behaves differently in Compatibility Mode than in current mode; the test document was in Compatibility Mode. If content controls don't work as required there, fallback is Word document protection (read-only sections containing the timestamps). The fallback is uglier but achieves the same outcome.

*Estimated time: 1–2 days plus verification.*

### Tranche 1 sign-off gate

After Steps 1–5 are complete and signed off, **a consolidated Tranche 1 walkthrough** repeats the full audio-to-Word-to-Save sequence end-to-end, covering all the bug fixes together. This catches any interaction effects between E13 and E6 that single-item testing missed. Only after this consolidated walkthrough does Tranche 2 begin.

### Step 6 — Help content sprint (Audio Transcription Guide + help-icon copy)

*Two days of writing, no code changes.*

**What we change.** Produce two pieces of content: (a) a full draft of the new Audio Transcription Guide replacing the current stale `AUDIO_TRANSCRIPTION_GUIDE.md`; (b) a tabular document mapping every help-icon location across the cleanup dialog, Speaker Panel, and routing buttons to its plain-English copy. Both authored as one piece by one writer for voice consistency.

**Targeted scenario tests.**
1. *Naive-reader test:* one external reader (someone who hasn't seen DocAnalyser) reads the Guide and articulates back what they think the workflow is. Surfaces tone issues, gaps, and assumed knowledge.
2. *Help-icon copy review:* read each help-icon entry against the F1 taxonomy and the Guide narrative for consistency.
3. *Coverage check:* every control identified in C6, E4, and H1 has a corresponding help-icon copy entry.

**Sign-off.** Ian reads the Guide end-to-end and confirms it accurately describes the workflow he wants users to follow. Help-icon copy table is approved before wiring begins.

*Estimated time: 2 days for writing, half a day for review.*

### Step 7 — Wire help icons into the cleanup dialog

**What we change.** Add (?) icons next to each section heading and each radio option in the cleanup dialog. Clicking opens a popup with the approved help-icon copy from Step 6. Pattern designed once (I1) and applied uniformly here for the first time.

**Targeted scenario tests.**
1. Each (?) icon is present and clickable.
2. Each popup shows the approved copy with no truncation, formatting issues, or wrong content.
3. Popups dismiss cleanly (click outside, Escape key, dedicated close).
4. The dialog itself remains usable after popups have been opened and closed multiple times — no focus issues, no leaked windows.

**Sign-off.** Ian opens the cleanup dialog and reads through every help icon. Confirms each one is helpful and matches the Guide.

*Estimated time: 1 day.*

### Step 8 — Cleanup dialog wording (C1–C4) and Speaker Panel rename (E2)

*Small text changes; quick wins.*

**What we change.**
- C1: top-of-dialog wording from *"N segments transcribed. Choose options below."* to the agreed plain-English version.
- C2: listener back-channels rewording (decision needed first).
- C3: Skip rewording.
- C4: Suggest-speakers help-popup wording (text already drafted, just wire it in).
- E2: Speaker Panel header from *"resolved/unresolved"* to *"named/yet-to-be-named"*; *Prev unresolved/Next unresolved* buttons renamed to *Prev unnamed/Next unnamed*.

**Targeted scenario tests.**
1. Open cleanup dialog: verify all four wordings are in place.
2. Run cleanup, open Word: verify Speaker Panel header reads *"N paragraphs · 0 named · N yet to be named"*.
3. Click *Next unnamed*: verify navigation behaviour unchanged.

**Sign-off.** Ian opens the dialog and the Speaker Panel and reads everything. Approves or sends back for refinement.

*Estimated time: half a day.*

### Step 8a — F.11a: speaker-bulk confirmation dialog (added 3 May 2026)

*Small addition to the Speaker Panel. Independent of Track Changes scope.*

**What we change.** Add a confirmation dialog that fires before *Apply names to whole document* commits. The dialog shows the proposed substitution and reminds the user that the heuristic's assignments are suggestions only.

**Targeted scenario tests.**
1. Click *Apply names to whole document*. Dialog appears with the substitution summary.
2. Yes → bulk apply proceeds. No → dialog dismisses without committing.
3. Wording matches Decisions Register F.11a seed copy.

**Sign-off.** Ian clicks the button on a fresh transcription, reads the dialog wording, confirms it lands well.

*Estimated time: half a day.*

### Step 9a — A3 + E10: Track Changes infrastructure (added 3 May 2026 — locked into Tranche 2)

*The largest single piece of new work in Tranche 2. Pulled from Tranche 3 into Tranche 2 per Ian's call to bring Corrections Lists into v1.7-beta scope.*

**What we change.** Word's Revisions API integration. Bulk operations — *Apply names to whole document*, applying a Corrections List during cleanup, and the post-hoc *Apply Corrections List to this document* (Step 10a below) — write changes as Word tracked changes rather than committing them directly. The user reviews per-paragraph using Word's native Accept/Reject UI before saving back to DocAnalyser. *Save edits to DocAnalyser* is refused if unresolved changes remain; user is prompted to accept or reject all first.

The default-on Track Changes preference is also added to Audio & Transcription Settings as part of this step.

**Targeted scenario tests.**
1. *Apply names to whole document* with Track Changes preference on: changes appear as tracked revisions in Word, not as direct edits. Native Accept/Reject works on each.
2. Click *Save edits to DocAnalyser* with unresolved revisions: save is refused, message advises resolving all revisions first.
3. Accept all revisions, save: round-trip back to DocAnalyser as normal.
4. Reject all revisions, save: paragraph headers revert to `[SPEAKER_X]` placeholders; user can re-assign individually via Speaker Panel.
5. Apply a Corrections List during cleanup with Track Changes preference on: same tracked-changes behaviour for word-level substitutions.
6. Turn Track Changes preference off, repeat the same operations: behaviour is direct (no tracking).
7. *Regression spot-check:* re-run the audio-to-Word-to-Save round-trip with various combinations of preference state and bulk operations. Confirm previously-working behaviour still works.

**Sign-off.** Ian runs both the speaker-bulk and Corrections List apply paths through Track Changes with the preference on and off; confirms the revisions UI, the save-refusal logic, and the round-trip all work as intended.

**Risk and fallback.** Word's Revisions API is well-documented but new code in a non-trivial integration. The 4–5 day estimate assumes a clean run; if API edge cases (compatibility mode, particular Word versions) surface, this can stretch. No fallback for Tranche 2 — if Track Changes proves unworkable in the timeframe, escalate to Ian for a re-scope decision (one option: ship Corrections Lists with the speaker-bulk-style confirmation dialog from Step 8a as a partial mitigation, defer full Track Changes to v1.7).

*Estimated time: 4–5 days plus verification.*

### Step 10a — D1a: Apply Corrections List to existing document (added 3 May 2026 — locked into Tranche 2)

*Pulled from Tranche 3 into Tranche 2 per Ian's call. Depends on Step 9a infrastructure being in place.*

**What we change.** Add a *"Apply Corrections List to this document"* action to the Source Document view. When invoked, the selected Corrections List is applied to the current document via the Track Changes infrastructure from Step 9a (so the user reviews the changes in Word before saving). Addresses the typical oral-history use case of a series of related interviews where a Corrections List entry added later needs to apply to documents processed earlier.

**Targeted scenario tests.**
1. Open a previously-cleaned document in Source Document view. Trigger *Apply Corrections List*. Choose a Corrections List that has entries matching content in the document.
2. Word opens (if not already open) showing the document; corrections are present as tracked changes.
3. Accept some, reject others, save. Document updates correctly per the user's choices.
4. Run on a document with no Corrections List entries matching content: action completes with a *"No matching corrections in this document"* message.

**Sign-off.** Ian processes a document with a Corrections List that didn't exist when the document was first transcribed; verifies the round-trip works end-to-end.

*Estimated time: 2 days.*

---

**Note on step ordering (3 May 2026).** Steps 8a, 9a, and 10a are inserted into the Tranche 2 sequence between the existing Step 8 and the existing Step 9. The original Steps 9, 10, 11 (welcome overlay, Speaker Panel + routing button help icons, split/merge confirmation dialogs) follow afterwards — their step numbers are unchanged but their position in time shifts. Motivation: Track Changes infrastructure (Step 9a) is shaken down before Step 11 (E7 split/merge), which has its own COM behaviour concerns; the welcome overlay and help-icon work (Steps 9 and 10) happens last in time so they correctly describe everything that's in place.

---

### Step 9 — E1 welcome overlay

**What we change.** First-open modal on the Speaker Panel explaining the three-window arrangement, the user's goal, and where to start. *Don't show again* tickbox. Links to the Guide via Help menu.

**Targeted scenario tests.**
1. Fresh install (or wiped preferences): open Word from a transcription. Speaker Panel opens; welcome overlay appears.
2. Click the Guide link: Guide opens in Help menu.
3. Tick *Don't show again*, dismiss overlay. Close Word. Repeat the Word-open flow on a different transcription. *Overlay should not appear again.*
4. Reset preferences: overlay reappears.

**Sign-off.** Ian performs the full first-time Word-open flow with the overlay visible and confirms it lands well.

*Estimated time: 1 day.*

### Step 10 — Help icons on Speaker Panel and routing buttons (E4 + H1)

**What we change.** Apply the same (?) icon pattern from Step 7 to every Speaker Panel control identified in E4 and to the routing buttons identified in H1.

**Targeted scenario tests.**
1. Each (?) icon present, clickable, shows correct copy.
2. The Speaker Panel itself remains usable — no focus issues, no leaked windows after popups.
3. The routing buttons help icons render correctly when the cleanup dialog is in routing-buttons-after-cleanup mode.

**Sign-off.** Ian opens both views and reads through every help icon.

*Estimated time: 1–2 days.*

### Step 11 — E7: split/merge confirmation dialogs

*The trickiest Tranche 2 item because of the sentence-boundary detection.*

**What we change.**
- *Sentence-boundary detection:* logic that identifies the sentence containing the cursor, with handling for edge cases (abbreviations, multiple punctuation, sentence-final ellipses, etc.).
- *Split rule:* the cursor sentence always becomes the first sentence of the new paragraph.
- *Split confirmation dialog:* shown on Enter inside a paragraph, displays the proposed sentence with first few words and `[MM:SS]`. Yes/No/*Don't show again for splits*.
- *Merge confirmation dialog:* shown on deletion of a paragraph break. Displays which speaker assignment will survive. Yes/No/*Don't show again for merges*.

**Targeted scenario tests.**
1. Place cursor at start of a sentence, press Enter: dialog shows the correct sentence, split lands cleanly.
2. Place cursor mid-sentence, press Enter: dialog shows the same sentence (the one containing the cursor), split moves that sentence to the new paragraph.
3. Place cursor at end of a sentence (immediately before the next sentence's start), press Enter: dialog shows the next sentence (since the cursor is technically inside it). User cancels, repositions one character back, tries again — dialog shows the correct sentence.
4. Test sentence-boundary detection on tricky cases: a sentence ending with *"Dr."*, a sentence ending with *"etc."*, a sentence with embedded `?` (rhetorical question mid-sentence).
5. Delete a paragraph break: merge dialog appears, shows the surviving speaker, user confirms.
6. *Don't show again* tickboxes: split-only dismissal does not affect merge dialogs and vice versa.
7. *Regression spot-check:* split/merge behaviour after E6 (content controls) still works correctly — splits preserve `[MM:SS]` integrity.

**Sign-off.** Ian performs five or six different splits and three or four merges across various paragraph types in a real transcript and confirms behaviour matches the rule.

**Risk and fallback.** Sentence-boundary detection accuracy is the failure mode. If edge cases are common enough that the dialog frequently shows the *wrong* sentence, the user experience is worse than the current "press Enter splits at cursor" behaviour. Mitigation: a fallback rule for ambiguous cases — if the sentence-boundary detector is unsure, the dialog shows the user the surrounding text and asks them to confirm where the split should go.

*Estimated time: 2–3 days.*

### Tranche 2 sign-off gate — the naive-user pass

After Steps 6–11 are complete and individually signed off, **a final consolidated naive-user pass** runs the full audio-to-edited-transcript workflow as if Ian were a first-time user. The Guide is read first; the welcome overlay is engaged; the cleanup dialog and Speaker Panel are explored only via their visible help. Anything that confuses or surprises is logged and either fixed or explicitly accepted as a known rough edge for the PhD user.

This is the moment to decide *ship vs one more pass*. If the naive-user pass is clean, the build is packaged as v1.7-beta and goes to the PhD user. If issues surface, they're triaged: pre-handover fix, or known-issue note in the welcome overlay.

*Estimated time: half a day, plus any fixes.*

---

## 6. Risk register

The five things most likely to slip the timeline:

**E13 (save round-trip stale views) is scoping-uncertain.** Step 2 above scopes this before Step 4 starts to commit to the actual time required. If the simple version, half a day for the fix; if the data-binding rework, several days. Worth being honest about this upfront rather than discovering it three days into Step 4.

**E6 (Word content controls) has API edge cases.** Word's content control API works differently in compatibility mode than in current mode. The screenshots show the test document is in Compatibility Mode. Need to verify content controls actually behave as required there before committing to this approach. Plan B if they don't: Word document protection (read-only sections containing the timestamps), which is uglier but works.

**E7 (sentence-boundary detection for split) has accuracy risk.** Whisper's punctuation isn't always reliable, especially around abbreviations and informal speech. The cursor-sentence rule depends on correctly identifying sentence boundaries. The targeted tests in Step 11 explicitly cover the tricky cases; if accuracy is poor, the fallback rule kicks in.

**The help content is more work than it looks.** Plain English that's actually clear is harder to write than technical English. The 2-day estimate for the Guide assumes a competent prose writer working efficiently; if iterations are needed for tone or accuracy, this can stretch. Mitigation: the naive-reader test in Step 6 catches tone issues early so they don't surface only at the Tranche 2 gate.

**G2 may surface that v1.7-alpha is less complete than it looks.** If Corrections Lists are scaffolded rather than wired, the *+ Correction…* button in the Speaker Panel is presenting a feature that doesn't work. That's a Tranche 1 item we haven't yet identified — needs to be either finished or hidden before handover. Can't estimate until G2 is done.

---

## 7. The packaging strategy

After Tranche 1 + Tranche 2 ship and the Tranche 2 naive-user pass is clean, the build goes to the PhD user as **DocAnalyser v1.7-beta**. *Beta* not *release* because:

- The Source Document / Thread Viewer editing path hasn't been re-walked since the changes (Word path was the focus).
- Stage 6 (AI processing on cleaned transcripts) hasn't been re-walked at all in this round.
- Tranche 3 items will continue to land in subsequent point releases.
- The PhD user will surface things we haven't anticipated; calling it beta sets the right expectation that feedback is wanted.

**What "beta" means concretely for the user:** the workflow is complete and reliable for the audio editing use case, but they should expect to find rough edges and they have a direct line to you for reporting them. A short *"Welcome to DocAnalyser v1.7-beta"* note pinned in the Help menu, listing what's known to be rough, manages expectations honestly without being defensive.

After the PhD user has worked with v1.7-beta for two to three weeks and the most-pressing of their feedback is incorporated, the next release is **v1.7** (no beta tag) — at which point Tranche 3 items are landing and the build is suitable for wider distribution.

---

## 8. What this strategy does not address

Several real considerations that need separate decisions:

- **The Source Document / Thread Viewer editing path** — not walked through in this session. May have its own set of items needing the same kind of cleanup. The PhD user can route to either, so the Source Document view also needs to be naive-user-comprehensible. **Recommendation: walk the Source Document path in a separate session, ideally before Tranche 1 starts so any bugs surface there are folded in.**
- **Stage 6 — AI processing on cleaned transcripts** — not walked through. Audio-linked summaries are the killer feature; if a naive user can't get to one easily, that's a packaging concern even if the workflow up to that point is clean.
- **The Audio & Transcription Settings dialog** — flagged as cluttered (A1) but not walked through in detail. Whether it's good enough for a first-time user to get oriented is unknown.
- **AssemblyAI's actual integration** — the entire AssemblyAI engine path was theorised but not tested. If the PhD user's first instinct is to try AssemblyAI for diarisation (which the Guide will recommend for many use cases), it needs to work end-to-end. Worth a separate quick verification.

These are not strategy gaps — they're scope acknowledgments. Each could expand the timeline if walking through them surfaces blockers; none have to delay Tranche 1 starting.

---

## 9. Decisions resolved 3 May 2026

All eight decision-points listed in the original draft of this section were resolved with Ian on 3 May 2026 in conversation with Claude. Summarised here for traceability; full details in `Roadmap/Audio_Editing_Design_Decisions_Register_2026-05-02.md` §M.

1. **Tranche scope confirmation — Confirmed.** Four-tranche structure unchanged. Tranche 2 grows in scope per items 7 and 8 below; no items move between tranches.
2. **F1 taxonomy lock — Pending Step 1.3.** Five-category structure provisionally agreed; confirmed in Step 1.3 before help-content authoring begins.
3. **A2 sub-question — Hard preference.** User must change Audio Settings to override; mitigated by A1 promoting the toggle in Settings.
4. **C2 — listener back-channels rewording — Resolved.** Candidate A's wording as the checkbox label; Candidate B's qualifier captured in help-icon copy.
5. **D1c — Reset to raw transcription — Defer to Tranche 4.** Conditional on G2 confirming Backups are wired.
6. **G3 — Thread Viewer vs Source Document naming — Resolved.** Source Document canonical for user-facing; code names unchanged.
7. **A3 prioritisation — Tranche 2 (locked).** Corrections Lists confirmed in v1.7-beta scope per Ian's call. Track Changes is essential for the Corrections List apply path. D1a (E.1) also pulled into Tranche 2. Three new Tranche 2 steps (8a, 9a, 10a) inserted into §5 above.
8. **Source Document path walkthrough — Folded into Step 1 (item 1.2).** Step 1 grows from half-a-day to roughly 2–3 days.

**No outstanding decisions remain before implementation begins.** Step 1 (G2 investigation + Source Document walkthrough + F1 taxonomy lock) is the entry point.

---

*Drafted by Claude on 2 May 2026 for review by Ian. Revisions expected.*
