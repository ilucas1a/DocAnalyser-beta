# Audio Transcript Workflow — End-to-End Walkthrough

**Date:** 28 April 2026 *(superseding the 28 April morning draft)*
**Status:** Reference document — describes the current workflow and where Enhancement 25 (Local Voice-Based Speaker Identification) lands within it, with the cleanup pipeline restructured to incorporate Corrections Lists and acoustic-first speaker identification
**Companion to:** `Voice_ID_Segmentation_Test_Plan_2026-04-27.md` and `AI_Transcript_Refinement_Spec_v3.docx` (v3 spec — see §12 for implications)
**Audience:** Anyone designing or implementing changes to the audio pipeline; future Ian returning to this work

---

## 1. Purpose

The test plan answers *which segmentation engine should we use*. The v3 spec answers *what AI-assisted refinement looks like on top of the local pipeline*. This document answers what sits between them: *how does the local pipeline itself need to change once voice-ID is reliable, and what does the user actually see at each stage*.

It exists because Enhancement 25 lands in the middle of an established pipeline and forces a structural decision about that pipeline that wasn't visible before voice-ID became viable: speaker boundaries from acoustic data ought to drive paragraph boundaries, not be overwritten on top of paragraph boundaries derived from heuristic guesses. That single architectural change has ripple effects through the cleanup dialog, the Corrections List capability, and the relationship between local cleanup and AI refinement.

The document walks through each stage as the user experiences it today, then describes what changes — first conceptually as *editing layers* (§4), then concretely as a revised cleanup pipeline and dialog (§5), then through the rest of the pipeline. A final section (§12) captures the changes this implies for the v3 spec.

---

## 2. Stage 1 — Source acquisition

**What the user does.** Loads audio via any available source: local file, YouTube URL, podcast (Apple Podcasts or RSS), Substack audio post, web video (Twitter/Facebook/Vimeo), or Google Drive file.

**What happens.** The platform-specific helper (`youtube_utils`, `substack_utils`, `podcast_handler`, `google_drive_handler`, etc.) extracts the audio file to local cache. `document_fetching.py` orchestrates this. A document record is created in the SQLite library with `audio_file_path` stored in metadata.

**What the user sees.** Progress indicator while audio is being acquired. No dialogs.

**Effect of Enhancement 25 or the new architecture:** None. This stage is unchanged.

---

## 3. Stage 2 — Transcription engine selection and run

**What the user does.** Nothing, if their engine is already configured. Otherwise sets the engine in Audio Settings (faster-whisper local, AssemblyAI cloud, OpenAI Whisper API, or Moonshine ONNX) and any related options (language, VAD, chunk size).

**What happens.** `audio_handler.transcribe_audio_file()` dispatches to the chosen engine. Results are cached by hash of `(audio_path, engine, model, language, use_vad)`.

**What the user sees.** Progressive segment display — text appears in the source pane as it's transcribed, in real time. Progress indicator. No dialogs unless something goes wrong.

**Output.** This is what the v3 spec calls **DRAFT_1**: a list of `entries` with `[start, end, text]` tuples and no speaker labels.

**Effect of Enhancement 25 or the new architecture:** None. Speaker handling and corrections happen entirely in the next stage.

---

## 4. The editing layers — a conceptual map

Before diving into the cleanup dialog, it's useful to name the distinct things that need editing in a transcript. They form layers, each with its own source of truth, its own affordances, and its own place in the pipeline. Conflating them — which the current pipeline arguably does — creates the architectural problems Enhancement 25 forces us to fix.

**Layer 1 — Word-level corrections (find-and-replace).** Common mistranscriptions of proper nouns, place names, technical jargon: "Quang Tri" misheard as "Kuan Chi", "Glenn Diesen" as "Glen Deesen", and so on. These are pure substitutions that any user processing similar material repeatedly will accumulate over time. They don't need AI to apply (find-and-replace is deterministic) and don't need acoustic data. The right place for them is *early* in the pipeline so downstream phases work on cleaner text.

This is what the v3 spec calls a **Corrections List** — a project-scoped collection of find/replace pairs, persisting across transcripts, growing as the user processes more material. The 30-Vietnam-War-interviews case is the canonical motivation: the first interview adds 40 corrections; by the tenth, most apply automatically and only a handful of new ones need to be added.

**Layer 2 — Sentence boundaries.** Where one sentence ends and the next begins. Today this is handled by the cleaner's Phase 2 (sentence consolidation) using gap thresholds and terminal punctuation detection. It's heuristic but works well in practice. The v3 spec proposes AI refinement as a tickbox for this layer (4.3) when finer accuracy is needed.

**Layer 3 — Speaker boundaries.** Where one speaker's turn ends and the next speaker's begins. Today this is heuristic (Phase 3). With Enhancement 25 it becomes acoustic — much more reliable, and the foundation everything downstream now depends on.

**Layer 4 — Paragraph boundaries.** Where paragraph breaks fall. These are *derived* from a combination of long gaps (Layer 2 data) and speaker changes (Layer 3 data). Critically, paragraph boundaries should be a function of the layers below them, not a parallel layer. Today's pipeline doesn't fully enforce this (see §5.3).

**Layer 5 — Speaker identity.** Who each speaker actually is — `Glenn Diesen` rather than `SPEAKER_00`. Today this is purely manual (the user types names in Section C of the cleanup dialog or assigns paragraph-by-paragraph in `speaker_id_dialog.py`). With Enhancement 25 it becomes mostly automatic via voiceprint matching, with manual fallback for unmatched clusters.

**Layer 6 — Word-level corrections of one-off errors.** Mistranscriptions specific to *this* recording (a name said only once, a foreign phrase, an unusual proper noun). These don't belong on the Corrections List — adding them would make future runs slower without benefit. They get fixed during the Word/Thread-Viewer review pass and stay local to the document.

**Layer 7 — Structural editing.** Splits, merges, free-form text edits done by the user during the Word/Thread-Viewer review pass after the cleanup pipeline has finished. Inherently human; no automation possible.

The architectural decision Enhancement 25 forces us to make is this: each layer should be handled at the right point in the pipeline, in the right order, with each layer informing the next. Layer 1 (corrections) → Layer 2 (sentences, mostly already done) → Layer 3 (speaker boundaries) → Layer 4 (paragraphs, derived from Layers 2+3) → Layer 5 (identity). Layers 6 and 7 are downstream of the pipeline entirely.

---

## 5. Stage 3 — The cleanup dialog (where most changes happen)

This is the central stage. Most of Enhancement 25 lands here, and most of the architectural decisions converge here.

### 5.1 What the dialog looks like today

The dialog is `transcript_cleanup_dialog.py`. It's non-modal, fixed-size at 470×530 pixels, centred on the parent window. It opens automatically when transcription completes (for both YouTube-sourced and local audio files).

**Today's layout, top to bottom:**

> **Transcript Clean-up**
>
> *Transcription complete*
> {N} segments transcribed. Choose options below.
>
> ┌─ A — Cleanup ─────────────────────────────────────┐
> │ ☑ Remove breath fragments  (uh, um, mm, hmm…)    │
> │     ☑ Keep listener back-channels as [annotations]│
> └────────────────────────────────────────────────────┘
>
> ┌─ B — Speaker identification ─────────────────────┐
> │ ⦿ Skip — assign manually later                    │
> │ ○ Suggest speakers automatically (heuristic, prov.)│
> │ ○ Detect speakers by voice  *(not available …)*   │
> └────────────────────────────────────────────────────┘
>
> ┌─ C — Speaker names ──────────────────────────────┐  ← only when B ≠ Skip
> │ Speaker 1: [______________________]               │
> │ Speaker 2: [______________________]               │
> │ Names are optional — you can assign speakers after│
> │ cleanup.                                          │
> └────────────────────────────────────────────────────┘
>
> [Run Cleanup]  [Skip cleanup]

**Key visual states today:**

- Section A's back-channel checkbox auto-disables when "Remove breath fragments" is unchecked.
- Section B's "Detect speakers by voice" radio is disabled, with `(not available — see Help for setup)` next to it. This is because `PYANNOTE_ENABLED = False` is hard-coded.
- Section C is hidden when "Skip" is selected and appears when either non-Skip option is chosen.
- The progress area is hidden by default and appears below Section C when cleanup is running.
- The button row starts with `[Run Cleanup] [Skip cleanup]` and is replaced after either action by `Open in: [Thread Viewer] [Microsoft Word]`.

### 5.2 What happens behind the radio buttons today

Clicking **Run Cleanup** launches a worker thread that runs `transcript_cleaner.clean_transcript()`. The current six-phase pipeline:

1. **Filler removal.** Discards filler segments; optionally keeps back-channels as bracketed annotations.
2. **Sentence consolidation.** Joins segments into sentences using gap thresholds and terminal punctuation.
3. **Heuristic speaker classification.** Assigns provisional `SPEAKER_A` / `SPEAKER_B` from text patterns. Marked `provisional=True`.
4. **Paragraph consolidation.** Groups sentences into paragraphs; new paragraph on gap-above-threshold or speaker change *as identified by Phase 3*.
5. **Pyannote alignment.** *Currently a no-op.* When previously active, this overwrote Phase 3's labels with `SPEAKER_00` / `SPEAKER_01` from acoustic data — but did *not* re-derive paragraph boundaries.
6. **Speaker name substitution.** Replaces internal IDs with real names from the user's `name_map`.

The output is what v3 calls **DRAFT_2**.

### 5.3 The architectural problem this pipeline has, and why Enhancement 25 forces a fix

When Phase 5 was active, the pipeline produced a quietly inconsistent artifact: paragraph boundaries (Phase 4) derived from heuristic speaker guesses (Phase 3), with acoustic speaker labels (Phase 5) layered on top. When the heuristic and the acoustic data agreed, all was well; when they disagreed, paragraph breaks fell in the wrong places relative to the real speaker turns. This was masked when Phase 5 was disabled because Phase 3's guesses were the only signal available.

With Enhancement 25 making voice-ID reliable, this inconsistency would surface immediately. The fix is to reorder the pipeline so each layer informs the next in the correct direction: corrections → sentences → speaker boundaries → paragraphs → identity. Acoustic data needs to land *before* paragraph consolidation, not after.

There's a parallel architectural decision the v3 spec also forces. v3 puts Corrections List application inside the AI refinement panel (tickbox 4.2), running as part of the AI pass. But Corrections List application is pure find-and-replace — it doesn't actually need AI. Putting it inside the AI pass means privacy-bound users who decline AI refinement also lose the corrections capability, even though the corrections themselves are entirely local. With Enhancement 25 making the local pipeline genuinely complete (clean text, named speakers, no cloud), Corrections List application should move *out* of the AI refinement layer and into the heuristic cleanup, where it can serve all users regardless of AI choice.

Both decisions point to the same revised pipeline.

### 5.4 The proposed revised pipeline

Six phases, restructured:

**Phase 1 — Filler removal.** *Unchanged.*

**Phase 2 — Sentence consolidation.** *Unchanged.*

**Phase 3 — Corrections List application.** *New, no AI.* Applies the user's selected Corrections List as case-aware, word-boundary-aware find/replace across all sentence text. Runs after sentence consolidation so word-boundary matching works on clean text. Pure deterministic substitution; no audio needed; no AI needed. If the user has not selected a Corrections List in the dialog, this phase is a no-op.

**Phase 4 — Speaker boundary detection.** *Restructured.* Two implementations gated by Section B of the cleanup dialog and (for the voice-based path) by hardware capability:

- *Voice-based path* (default when available): the chosen segmentation engine (winner of the Voice ID Segmentation Test) identifies acoustic speaker change points as a `SpeakerTimeline`. Then voiceprint matching: each cluster's audio is run through CAM++, the resulting voiceprint is compared against saved voiceprints in the SQLite `speakers` table, and matches above the auto-confirm threshold rename the cluster to the saved name. Matches in the prompt-for-review band are tagged for the post-cleanup review dialog (§5.6 ii). Clusters with no confident match keep their `SPEAKER_X` placeholder.
- *Heuristic fallback* (when voice-ID unavailable or skipped, or hardware below capability threshold): the existing text-pattern classifier runs as it does today, producing provisional `SPEAKER_A` / `SPEAKER_B` labels.

Either way, Phase 4 produces speaker boundaries. The voice-based path produces *acoustically grounded* boundaries with most clusters already named; the heuristic path produces *pattern-guessed* boundaries with placeholder labels.

**Phase 5 — Paragraph consolidation.** *Behaviour unchanged, source restructured.* New paragraph on gap-above-threshold or speaker change as identified by Phase 4. Phase 5 doesn't need to know whether Phase 4's boundaries are acoustic or heuristic — both come through the same `SpeakerTimeline` interface.

**Phase 6 — Speaker name substitution.** *Unchanged in behaviour.* Replaces remaining `SPEAKER_X` placeholders with names from the user's `name_map` (typed in Section C). Voice-ID-confirmed names from Phase 4 are left untouched.

The key invariants this pipeline enforces:

- Corrections happen before any structural decisions, so structure is built on already-corrected text.
- Speaker boundaries always come from real data (acoustic or heuristic, but never overwritten downstream).
- Paragraph boundaries are always consistent with whatever speaker boundaries the user chose (voice-based or heuristic).
- The pipeline produces internally consistent output regardless of which branches run.

### 5.5 The proposed revised dialog

Three changes to the dialog UI follow from this:

**Change 1: Section A gains a Corrections List dropdown.**

> ┌─ A — Cleanup ─────────────────────────────────────┐
> │ ☑ Remove breath fragments  (uh, um, mm, hmm…)    │
> │     ☑ Keep listener back-channels as [annotations]│
> │                                                    │
> │ Apply corrections from list:  [None ▾]  [Edit…]  │
> └────────────────────────────────────────────────────┘

The dropdown defaults to `None`. When opened, it lists all available Corrections Lists — starting with the bundled `General` list (per v3) and any user-created project-scoped lists. The `[Edit…]` button opens the Corrections Lists management UI (Settings → Corrections Lists, per v3 §"List management UI"). Selecting any list other than `None` enables Phase 3 for the run; selecting `None` makes Phase 3 a no-op.

**Change 2: Section B's voice-detection radio becomes available, with engine indication.**

> ┌─ B — Speaker identification ─────────────────────┐
> │ ○ Skip — assign manually later                    │
> │ ○ Suggest speakers automatically (heuristic, prov.)│
> │ ⦿ Detect speakers by voice  *(Lightweight engine)* │
> └────────────────────────────────────────────────────┘

The "Detect speakers by voice" radio becomes the default (`⦿`). The italic suffix indicates which engine will run on this machine — *Lightweight* by default, *High quality* if the user has switched to it in Audio Settings (which is only available on capable hardware per the test plan §13 outcome 1). On machines that don't even support Lightweight (extremely unlikely given the test plan thresholds, but possible), the radio falls back to disabled with a tooltip pointing to F1 help. The "Suggest automatically" heuristic option remains for users who explicitly want to skip voice-ID even though it's available.

**Change 3: Section C is essentially unchanged**, but its meaning shifts.

When voice-ID is selected and runs successfully, most paragraphs arrive in the editor already named via voiceprint matching, so the Speaker 1 / Speaker 2 fields in Section C only matter for residual unmatched clusters. The fields stay (for the case where the user is processing audio of speakers not previously enrolled) but the wording of the helper text gains a small note: *"For voiceprint-matched speakers, names will be filled in automatically."*

### 5.6 New dialog moments introduced by Enhancement 25

Three new interactions appear around (not inside) the cleanup dialog. Each needs design attention before implementation.

**(i) First-run model download.** First time a user selects "Detect speakers by voice" with no models cached:

> **Voice identification — first-time setup**
>
> Voice identification needs two small models (~40 MB combined) which will be downloaded once and stored locally. Audio never leaves your machine.
>
> [Download now]  [Cancel]

After download: control returns to the cleanup dialog and Run continues. After cancel: radio reverts to "Suggest automatically" with a tooltip explaining why. Infrastructure largely exists in `hf_setup_wizard.py`; gets simplified for the new engine (no token, no licence).

**(ii) Post-cleanup voiceprint review.** After the cleanup pipeline finishes, but *before* the routing buttons appear, if any clusters fall in the prompt-for-review band a small overlay opens:

> **Voice identification — review needed**
>
> Speakers automatically identified:
>   ✓ Glenn Diesen  (3 paragraphs, high confidence)
>   ✓ Mohammad Marandi  (12 paragraphs, high confidence)
>
> Possible matches:
>   ? Speaker 0 (8 paragraphs)  →  Probably Lawrence Wilkerson  (62%)  [Confirm] [Reject]
>
> Unidentified:
>   • Speaker 2 (4 paragraphs)  [Save voiceprint as: ___________ ]
>
> [Done — open transcript]

This is the single most important new piece of UX. It's where voiceprint enrollment happens, where low-confidence matches get human confirmation, and where the user sees what the matcher decided. Non-modal so the user can scrub the transcript while deciding.

If everything matched strongly, this dialog appears in a simpler form ("All speakers identified — click Done"). If nothing matched at all (first-time run with no enrolled speakers), it offers bulk enrollment ("No matches yet — save voiceprints for next time?").

**(iii) Engine choice in Audio Settings + capability F1 help.** Per the test plan §13 outcome 1: a new dropdown in Audio Settings for "Speaker identification engine: *Lightweight* (default) / *High quality* (requires capable hardware)". Show-but-disabled on below-capability machines with F1 help explaining why and what alternatives exist (AssemblyAI cloud; manual SpeakerPanel labelling).

---

## 6. Stage 4 — Routing choice

After cleanup completes (or is skipped), the dialog's bottom row changes to:

> Open in:  [Thread Viewer]  [Microsoft Word]

These are two complete editing environments, not separate quality tiers. Users choose based on what they're doing with this transcript.

**Thread Viewer** keeps everything inside DocAnalyser. Audio playback synchronises with the transcript, the structured paragraph editor handles word-level corrections and paragraph splits, the SpeakerPanel handles bulk speaker assignment, and AI prompts can be run on the transcript inline. Best for transcripts you're going to use within DocAnalyser's own workflow.

**Microsoft Word** exports the transcript to `.docx` formatted as `[MM:SS]  [Speaker]:  text`, opens it in Word, and launches the companion audio player alongside. Best for long-form structural editing, free-form reorganisation, or producing a publication-grade artefact.

**Effect of the new architecture:** The routing choice itself is unchanged. But the *contents* arriving in either environment are dramatically different — see §7 and §8.

---

## 7. Stage 5a — The Thread Viewer path

### 7.1 What the user sees on arrival

Thread Viewer opens with the transcript displayed as a sequence of paragraph blocks. Each paragraph carries:

- A grey timestamp header `[MM:SS]`.
- A bold speaker label (`Glenn Diesen:`, or `SPEAKER_00:` if unresolved).
- Paragraph text with sentence-level click-to-seek.

Above the transcript: the Audio Playback control bar with speaker filter dropdown, Edit transcript / Save edits toggle, Audio links button, Merge / Split buttons.

### 7.2 Speaker identification inside Thread Viewer

The two-phase workflow in `speaker_id_dialog.py` (modal naming dialog → non-modal click-driven assignment panel) is unchanged. With voice-ID active upstream, this workflow is invoked only when there are still unresolved `SPEAKER_X` clusters — which is increasingly the residual case rather than the dominant work.

### 7.3 Editing modes

- **Word corrections** — click ✏ to enter edit mode, fix mishearings inline, click 💾 to save.
- **Paragraph splits** — Enter or click ✂ in edit mode; split happens at the nearest sentence-ending punctuation, with live preview.
- **Paragraph merges** — click ⊕ in edit mode; merges current paragraph with the next.
- **Speaker rename** — click a speaker label; small dialog opens (per-paragraph rename only — bulk rename of all paragraphs sharing a label is a known gap).
- **Add to Corrections List** — *new, ties to the cleanup pipeline restructure.* When the user finds a recurring mistranscription during review, they highlight the error, click "Add to Corrections List" (button to be added to the Audio Playback toolbar), and a small dialog opens with the highlighted text and suggested correction. They edit if needed, choose which Corrections List to add to, and one click adds the entry. This matches v3 §9 ("Live Corrections List expansion") and is what makes the corrections capability *grow* over time rather than being a static asset.

### 7.4 Effect of the new architecture

Two effects:

**Speaker ID work shrinks.** Most paragraphs arrive already named via voiceprint matching. Speaker assignment goes from 5–15 minutes of work for a 60-minute interview down to maybe 30 seconds to 2 minutes for residuals.

**Word-level errors shrink too**, *but only over time*. The first time a user processes audio in a new domain, mistranscriptions of proper nouns are still scattered through the transcript. They fix them inline as today. The new behaviour is that they can promote any of those fixes to the Corrections List. The next interview in the same domain: those corrections apply automatically during cleanup. By the tenth interview, most domain-specific errors are pre-corrected and only a handful of new ones remain. This is the 30-Vietnam-War-interviews dynamic.

---

## 8. Stage 5b — The Microsoft Word path

### 8.1 What the user sees on arrival

Three things open in sequence:

**Microsoft Word** opens the exported `.docx`. Document begins with a title heading, a "Document Information" block (audio path, date, engine), a small grey usage note about keeping `[MM:SS]` timestamps intact, and then one paragraph per transcript entry formatted as:

> [00:00]  **Glenn Diesen:**  Welcome to the Geopolitics & Empire podcast…
>
> [00:34]  **Mohammad Marandi:**  Thank you for having me…

`[MM:SS]` is plain grey 8pt text (not a hyperlink), speaker label is bold, body is normal weight.

**Companion player** (`companion_player.py`) launches as a separate small window. Playback controls, draggable slider, "Jump to" text field. Runs as `CREATE_NO_WINDOW` subprocess.

**Speaker Panel** (`word_editor_panel.py`) opens as always-on-top non-modal panel. Polls Word's COM interface every 500 ms to track cursor position and highlight the matching entry row. Badge shows `● Word linked` / `○ Word not linked`.

### 8.2 What the user does

The mental model: read in Word, listen in companion player, assign in Speaker Panel.

- **Per-paragraph speaker assignment.** Cursor in paragraph in Word → click name button in Speaker Panel → COM command navigates Word to the right paragraph using the `[MM:SS]` token as anchor → replaces the speaker label inline.
- **Bulk substitution.** "Apply names" runs `wdReplaceAll` for each name pair.
- **Structural edits.** User works in Word naturally (splits via blank lines, merges via deleting line breaks, free-form text edits). After a merge, user clicks "Refresh ¶" in the Speaker Panel to demote orphaned timestamp tokens.
- **Save back.** Save in Word → click "Save to DocAnalyser" in the Speaker Panel → panel parses the .docx, reconstructs entries using `[MM:SS]` anchors, calls `update_transcript_entries()`.
- **Add to Corrections List.** *New, parallel to §7.3.* The Speaker Panel gains an "Add to Corrections List" button. User selects the error in Word, clicks the button, the same Corrections List dialog as the Thread Viewer opens, with the same behaviour — edit the suggested correction, choose the list, optionally apply to current document. This is v3 §9 implemented per the new architecture.

### 8.3 Effect of the new architecture

Same shape as Thread Viewer: most paragraphs arrive named. The Speaker Panel needs a small change so it distinguishes auto-named paragraphs from unresolved ones — probably a per-entry metadata flag carried alongside `entries`, surfaced in the panel as "12 paragraphs auto-named — 3 need review." This gives the user a focused worklist instead of a wall of paragraphs.

The Add to Corrections List button is the bigger change. It transforms the Word path from an editing-only environment into a learning loop — fixes made here pay forward into the next document.

---

## 9. Stage 6 — AI processing (optional)

Once the transcript is cleaned and speakers are resolved, the user can run AI prompts on it. Common prompts: dotpoint summary with quotes and timestamps, key takeaways, follow-up Q&A. The `[SOURCE: "..."]` markers in AI output get rendered as clickable `▶ Jump to MM:SS` links in Thread Viewer.

**The v3 AI Refinement panel.** v3 proposes a separate AI Refinement step between heuristic cleanup and final import (DRAFT_2 → DRAFT_3 in v3 terminology). With the new architecture, the v3 panel's role shrinks but doesn't disappear:

- **Tickbox 4.1 (typo detection)** — still useful. AI scans for context-mismatched words. Unaffected.
- **Tickbox 4.2 (apply Corrections List)** — *moved out of the AI panel into the cleanup pipeline (§5.4 Phase 3).* What remains in the AI panel is the *Provisional Corrections discovery* layer: AI scans the transcript for likely proper-noun errors not yet in the user's Corrections List, presents them in the v3 §5.5 review dialog, and the user decides Promote / Accept once / Dismiss. This is opt-in — privacy-bound users skip it entirely; users who tolerate AI get the bonus of intelligent suggestions for what to add to their list.
- **Tickbox 4.3 (sentence boundary refinement)** — still useful. Heuristic Phase 2 catches the common cases; AI catches the subtler ones.
- **Tickbox 4.4 (paragraph refinement)** — *role reduced.* With voice-ID giving paragraph boundaries acoustic grounding, the AI is now refining mostly-correct boundaries rather than fixing wholesale errors. The `{MM:SS}` safety check (v3 §"Implementation notes") still applies. Most of v3 §4.4's value moves to the case where voice-ID is *not* used (heuristic path) — which is exactly where AI refinement of paragraphs is most needed.
- **Tickbox 4.5 (assign speakers)** — *role substantially reduced.* When voice-ID has named most clusters, this tickbox effectively becomes "AI re-attribution of low-confidence paragraphs the voice-ID layer flagged" rather than "AI speaker assignment from a blank slate." Still useful for the residual 5–10% of paragraphs, but no longer the primary mechanism.

**Effect of the new architecture:** AI refinement remains a genuine value-add for users who want it, but it's no longer load-bearing for any user. A privacy-bound user gets a complete usable transcript from local cleanup alone (corrections applied, voice-ID matched, paragraphs correctly bounded). AI refinement is what it should be: optional polish.

---

## 10. Before-and-after, end-to-end

For a representative case — tenth interview in a 30-interview Vietnam-veterans project, both speakers (interviewer and one veteran) previously enrolled, well-developed Corrections List for the project — the end-to-end experience compresses dramatically:

| Stage | Today | With new architecture |
|---|---|---|
| Source acquisition | Same | Same |
| Transcription | ~5–10 min compute, no UI work | Same |
| Cleanup dialog | Tick A options, Skip B (no voice-ID), click Run | Tick A options, select Corrections List in A, leave B as default (voice-ID), click Run |
| Cleanup processing | ~5 sec (heuristic only) | ~30–60 sec (corrections + heuristic + segmentation + voiceprint match) |
| Voiceprint review dialog | — *(does not exist)* | ~10–15 sec — "All speakers identified, click Done" |
| Open in Thread Viewer / Word | Transcript with provisional SPEAKER_A/B and ~40 mistranscribed proper nouns scattered through it | Transcript with named speakers throughout, ~3–5 mistranscribed proper nouns remaining (only the new ones not yet in the list) |
| Speaker assignment | 5–15 min manual click-driven | 0–1 min (residual cases only) |
| Word corrections | ~10–20 min fixing the 40 mistranscriptions | ~2–3 min fixing the 3–5 new ones, with 2–3 of those promoted to the Corrections List for next interview |
| AI summarisation | Works on transcript with possibly-correct speakers and uncorrected place names | Works on a clean, named, corrected transcript |
| **Total user attention** | ~20–40 min hands-on | ~5–10 min hands-on |

Compute cost goes up modestly (segmentation runs, corrections are applied). User attention drops by roughly an order of magnitude on mature projects. Privacy is preserved throughout.

For a *first* interview in a new project (no Corrections List yet, no enrolled speakers), the new architecture's compression is smaller — there's nothing to apply automatically. But the corrections and voiceprints captured during that first interview compound: by the third or fourth interview, the dynamic is in full swing.

---

## 11. Seams that need design attention before implementation

In priority order:

**Seam 1 — Post-cleanup voiceprint review dialog (§5.6 ii).** Single most important new piece of UX. Needs proper mockup, layout decisions for matched / possibly-matched / unmatched, and confirmation about whether the dialog appears every run vs only when there's something to review. Belongs in the formal Enhancement 25 design.

**Seam 2 — Corrections List dropdown in cleanup dialog Section A (§5.5 Change 1).** Dropdown UI, "Edit lists…" button wiring, default behaviour (None vs auto-apply last-used). Belongs in the formal design for Corrections Lists, which arguably should be its own enhancement (see §12).

**Seam 3 — Add to Corrections List button in Word panel and Thread Viewer (§7.3, §8.2).** The cross-cutting button that makes the corrections capability grow. UI design should be consistent across both editing environments. Same dialog, different launch points.

**Seam 4 — First-run model download (§5.6 i).** Conceptually straightforward; infrastructure mostly exists from `hf_setup_wizard.py`. Belongs in the formal Enhancement 25 design.

**Seam 5 — Engine choice in Audio Settings + capability F1 help (§5.6 iii).** Per test plan §13. F1 help content needs writing carefully so it doesn't read as gatekeeping.

**Seam 6 — Word path Speaker Panel awareness of auto-named paragraphs (§8.3).** Small but real change: panel needs to know which entries were auto-named so it can prioritise unresolved ones.

**Seam 7 — Confidence thresholds (auto-confirm / prompt-for-review / reject).** Defaults from empirical data on Ian's test corpus during the segmentation tests. Test plan §10 already provides for this.

**Seam 8 — SQLite schema additions.** Two new sets of tables: `speakers` + `document_speaker_matches` for voice-ID; `corrections_lists` + `corrections` per v3. Both piggyback on existing SQLite migration patterns.

**Seam 9 — Prospective enrollment (Speakers Library).** Bulk-enrol voiceprints from clean audio samples. Useful for Ian's repeat-subjects use case (Glenn Diesen, Marandi, Wilkerson, etc.). Deferred to v2 of Enhancement 25 unless test data shows the post-cleanup-only path is too slow to bootstrap.

---

## 12. Implications for the v3 spec

The new architecture requires specific changes to v3, which is currently locked. When v3 is unlocked for development (it should be revised to v3.1 to capture these), the changes are:

**Change A — Move Corrections List application out of the AI Refinement panel.** v3 §4.2 currently describes Corrections List application as a tickbox in the AI Refinement panel applied during the AI pass. In v3.1: Corrections List application moves into the cleanup pipeline (Phase 3 per §5.4 of this document) as a non-AI step, exposed as a dropdown in Section A of the cleanup dialog.

**Change B — v3 §4.2 retains only the Provisional Corrections discovery.** What remains in the AI Refinement panel under tickbox 4.2 is the AI-driven discovery of likely proper-noun errors not yet in the user's Corrections List. The Provisional Corrections review panel (v3 §5.5) is unchanged in structure but is now opt-in via a tickbox dedicated to Provisional Corrections discovery, rather than being a side-effect of "Apply Corrections List."

**Change C — Tickbox 4.5 (Assign speakers) becomes an AI re-attribution layer.** v3 §4.5 currently reads as full AI speaker assignment. v3.1 reframes it: with voice-ID upstream having named most paragraphs, 4.5's role is re-attribution of low-confidence paragraphs flagged by the voiceprint matcher. The role definitions and AI's role-mapping logic remain; the input is just a mostly-named transcript instead of a blank-slate one.

**Change D — Tickbox 4.4 (Paragraph refinement) language updated.** v3 §4.4 should note that paragraph boundaries are now grounded in acoustic data when voice-ID ran upstream, so AI refinement is correcting subtle issues rather than rebuilding structure. The `{MM:SS}` safety constraint (v3 "Implementation notes") still applies.

**Change E — Pipeline ordering in v3 "Implementation notes" updated.** The current pipeline ordering ("Corrections List → paragraphs → sentences → speakers → typos") within the AI pass becomes simpler — Corrections List is no longer in the AI pass at all. The new AI-pass ordering becomes: Provisional Corrections discovery (if ticked) → paragraphs → sentences → speakers → typos.

**Change F — DRAFT framework retained but redefined.** DRAFT_1 (raw transcription) and DRAFT_3 (post-AI) are unchanged. DRAFT_2 (post-heuristic-cleanup) is now richer: it includes Corrections List application and voice-ID-grounded speaker boundaries, not just heuristic cleanup. This is consistent with v3's "everything that follows is additive" principle, just with more actually happening before the AI step.

**Sequencing recommendation.** Three pieces of work fall out of all this:

1. *Corrections Lists capability.* Independent of voice-ID. Useful immediately for the 30-interview Vietnam-veterans case. Could be its own enhancement (Enhancement 26?), shipped before Enhancement 25 lands. The schema, the dropdown, the Add-to-list button across both editors, and the Settings management UI are all build-able and testable without any segmentation engine in place.

2. *Voice-ID engine and pipeline restructure (Enhancement 25).* Awaits the segmentation test results. Lands after 1.

3. *AI Refinement (v3.1).* Awaits both 1 and 2 — its scope is now defined relative to what they leave behind. Lands last.

Splitting Corrections Lists out as its own enhancement gives Ian a useful capability immediately, builds confidence in the SQLite schema patterns, and means by the time Enhancement 25 lands, the corrections layer is already mature.

---

## 13. What this document does not cover

- The internal architecture of the chosen segmentation engine — that's the test plan's domain.
- PyInstaller bundling implications of new packages and ONNX models — the formal design once the engine is chosen.
- AssemblyAI cloud diarisation path integration — unaffected by this work and remains the cloud-only alternative.
- Detailed UI mockups for the new dialogs (post-cleanup review, Corrections List management, Add-to-list dialog) — to be done as part of the formal designs, ideally on actual reference hardware.
- The full text of the v3.1 update — captured here as a list of changes (§12) but the actual rewriting of v3 happens when v3 is unlocked for development.

---

*Walkthrough drafted by Claude in collaboration with Ian Lucas, 28 April 2026 (afternoon revision incorporating the architectural decision to move Corrections Lists into the heuristic cleanup pipeline). Companion to the segmentation test plan dated 27 April 2026 and the AI Refinement Spec v3 dated 23 April 2026. Feeds into the formal Enhancement 25 design document, the Corrections Lists enhancement (proposed as Enhancement 26), and the eventual v3.1 of the AI Refinement spec.*
