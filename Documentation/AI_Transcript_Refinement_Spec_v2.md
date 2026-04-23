# AI-Assisted Transcript Refinement — Specification v2

**Drafted:** 22 April 2026
**Status:** Design ready for review, then roadmap commitment
**Target:** Near-term implementation (next beta cycle)

This document specifies an AI-assisted refinement layer added to DocAnalyser's existing audio transcription pipeline. It sits between the heuristic cleanup (current behaviour) and the Word-based editing workflow (current behaviour), both of which it leaves unchanged. The refinement layer is entirely optional per transcript.

## End-to-end workflow

### 1. Audio import

User loads an audio file into DocAnalyser via the usual pathways (local file, drag-and-drop, URL, podcast, subscription, etc.).

### 2. Transcription

DocAnalyser activates the selected transcription engine (Faster Whisper local, OpenAI Whisper cloud, AssemblyAI, etc.) and produces a raw timestamped transcript. Call this **DRAFT_1**.

### 3. Cleanup dialog opens

When DRAFT_1 is returned, the existing transcript_cleanup_dialog.py opens. The current heuristic cleanup via transcript_cleaner.py runs through its six-phase pipeline and produces an improved version with better punctuation, sentence structure, and paragraph structure. Speakers are labelled SPEAKER_A, SPEAKER_B, etc. by the existing heuristic. Call this version **DRAFT_2**. DRAFT_2 is the unchanged baseline output — everything that follows is additive.

### 4. AI Refinement panel (NEW)

The dialog now displays DRAFT_2 and adds an **AI Refinement** panel below the existing controls. The panel is collapsed by default so users who don't want AI assistance can proceed unchanged. Expanding it reveals five independent tickboxes:

**4.1 — Check for likely misheard words (context-based typos)**

Scans for words or phrases that are grammatically valid but don't fit the surrounding context — e.g. "He was shot in his arm and his back, and his *Congrats* carried him out of the DMZ." Excludes known project-specific errors (those are handled by 4.2). Suggestions appear in DRAFT_3 inline as `[Did you mean: comrades]` in coloured font adjacent to the flagged word, so the user can accept or reject each during the Word review pass.

**4.2 — Apply Corrections List**

When ticked, the user is asked to select a named Corrections List (see "Corrections Lists" section below). Each correction in the list is applied throughout the transcript. This runs *before* 4.1 so repeated project-specific errors don't clutter the typo-suggestion output.

During the AI pass, any new name-place-phrase errors the AI suspects but which aren't in the selected Corrections List are collected in a **Provisional Corrections List** for later review in step 6.

**4.3 — Refine sentence boundaries**

AI reviews sentence breaks and proposes corrections where punctuation landed in the wrong place. Example: a period inserted mid-thought where the speaker paused but hadn't finished their sentence; or a missing break where two sentences run together. Only affects punctuation within existing paragraphs — does not move content between paragraphs.

**4.4 — Refine paragraph structure**

AI reviews paragraph boundaries and proposes:
- **Splits**: paragraphs that contain two speakers, or paragraphs where a single speaker changes topic substantially
- **Merges**: consecutive one-sentence paragraphs from the same speaker that would read better combined

**Hard safety constraint:** every proposed split point must coincide with an existing `{MM:SS}` sentence-level timestamp marker. Splits mid-sentence are forbidden and validated against in code before being applied — this preserves audio sync. Merges preserve all `{MM:SS}` markers from both source paragraphs.

**4.5 — Assign speakers**

When ticked, the user is asked to define the roles present in this interview. The dialog presents two default rows pre-populated — "Interviewer" and "Interviewee" — with an "Add another role" button for panel discussions or audience Q&A. For each role, the user enters the person's name: e.g. `Interviewer = Dung`, `Interviewee = Biff`, `Audience member = Harold`.

The AI operates on roles internally (interviewer, interviewee, etc.) rather than names, and the dialog maps roles to names on output. This means if the user got the role mapping backwards, one dropdown flip corrects every assignment in the transcript at once.

If the transcription engine already returned native speaker labels (AssemblyAI diarization, etc.), the AI pass uses those as a starting point rather than regenerating from scratch.

### 5. Cost preview and execution

Before the AI pass runs, the dialog shows a cost estimate based on transcript length, selected tickboxes, and currently-selected AI provider — e.g. `Estimated cost: $0.15 on Claude Sonnet, or select Gemini Flash for $0.02`. This uses the existing cost_tracker.py pricing data.

The refinement works with any AI provider in the existing registry, including local Ollama models — important for users working with sensitive interview material where cloud AI is inappropriate.

User clicks **Refine**. A progress indicator shows what the AI is doing (typos, corrections, sentence boundaries, paragraphs, speakers) as it works. The result is **DRAFT_3**.

If DRAFT_3 is unacceptable for any reason, a **Discard AI Refinements** button reverts to DRAFT_2 and the user proceeds as if the refinement had never been offered.

### 6. Confidence-marked output

DRAFT_3 displays AI changes with confidence tiers:

- **High confidence**: applied silently (no inline marker); change is visible only as the improved text
- **Medium confidence**: marked with a subtle coloured indicator (e.g. yellow dot in the margin)
- **Low confidence**: marked with a stronger indicator (e.g. red dot) and, for 4.5 speaker assignments, includes a short `{AI: low conf}` note

These markers are written into DRAFT_3 in a form that survives the transition into Word, so during the Word review pass (step 8) the user's eye is drawn to the uncertain cases rather than forced to re-read everything. The markers are stripped on final save so the canonical transcript in DocAnalyser's library is clean.

### 7. Import to DocAnalyser

DRAFT_3 is imported as the canonical transcript. The AI-applied speaker roles become entry metadata — the word_editor_panel treats the transcript as already having a speaker layer applied (with confidence markers where relevant), rather than re-prompting for speaker identification.

A one-time warning message appears with a "Don't ask me again" checkbox:

> AI refinements have been applied to this transcript. Please check suggestions marked in yellow or red against the audio before finalising. AI can make mistakes, especially on accents, proper nouns, and back-channel speech.

### 8. Word review pass

User selects Edit in Word as now. Word opens with DRAFT_3 loaded; the companion audio player opens alongside. The user reviews, using the confidence markers as a prioritisation guide — red first, yellow second, high-confidence assumed correct unless something stands out.

### 9. Live Corrections List expansion

During the Word review pass, when the user identifies a repeated error not yet in the Corrections List (e.g. "Kuan Chi" → "Quang Tri"):

- They highlight the error in Word
- Click an **Add to Corrections List** button in the word_editor_panel
- A small dialog appears showing the highlighted text, a suggested correction, and a dropdown to choose which Corrections List to add it to (defaults to the one used in step 4.2, or offers to create one if none is associated with this document)
- One click adds the entry and optionally applies the correction throughout the current document

In the same session, the Provisional Corrections List items from step 4.2 appear in a review queue in the panel — the user can promote any of them to the main Corrections List with one click, or dismiss.

### 10. Finalisation

User saves edits from Word back to DocAnalyser via the existing word_editor_panel save mechanism. DRAFT_3 — now with user corrections applied, confidence markers stripped, Corrections List grown — becomes the canonical transcript in the DocAnalyser library, with audio link intact and all native editing capabilities available going forward.

---

## Corrections Lists

### Concept

A Corrections List is a project-scoped collection of known error-to-correction pairs that grows over time as the user processes more transcripts within the same subject area. First Vietnam War interview: user builds up ~40 corrections. Tenth Vietnam War interview: most corrections apply automatically; only a handful of new ones need to be added.

### Storage

Corrections Lists are stored in the SQLite database in two new tables:

- `corrections_lists` (id, name, description, workspace_id, created_at, updated_at)
- `corrections` (id, list_id, original_text, corrected_text, case_sensitive, word_boundary, notes, created_at)

The `workspace_id` column integrates cleanly with the planned Workspaces feature (Enhancement 13). If workspaces are enabled, a Corrections List is workspace-scoped by default but can be promoted to global.

JSON export/import support is provided for sharing lists between users, using the existing `.docanalyser` package format (Enhancement 1).

### Initial MVP: matching rules

For the first release, corrections are simple find-and-replace pairs with two options:

- **Case sensitive** (default: off — most mis-transcriptions are already lowercase)
- **Word boundary** (default: on — prevents "Song" matching inside "Songkhla")

Context-aware matching (e.g. "only replace 'Song' when it appears near 'Vietnam' or 'guide'") is explicitly deferred as a v2 refinement. The MVP handles the 90% case; the long tail can be addressed when we see real usage.

### Provisional Corrections List

During the AI pass (step 4.2), the AI may identify likely proper-noun errors that aren't in the current Corrections List — e.g. the AI might spot "Lingbing" as a suspicious place name even if no-one has yet added "Lingbing → Ninh Binh" to any list. These provisional suggestions are collected separately and presented to the user in step 9's review queue. The user promotes the useful ones; dismisses the false positives.

### List management UI

Corrections Lists are managed via a new entry in Settings → **Corrections Lists**. This is a simple table view: list name, entry count, last updated, buttons for Add/Edit/Delete/Export/Import. Implementation can reuse the existing prompt library UI patterns (prompt_tree_manager.py) as a starting point — both are "user-curated collections of small text items" and have similar ergonomics.

---

## Implementation notes

### Pipeline ordering

Within the AI pass, operations must run in this order to avoid feedback loops and lost work:

1. **Corrections List (4.2)** — applies known fixes first, removes noise
2. **Paragraph refinement (4.4)** — restructures on clean text
3. **Sentence refinement (4.3)** — fine-grained within each paragraph
4. **Speaker assignment (4.5)** — labels after structure is settled
5. **Typo detection (4.1)** — last pass over the finished text, so suggestions are surfaced on the final paragraph structure

### AI provider requirements

- Must accept structured JSON input and return structured JSON output (for confidence-marked changes)
- Must handle transcripts up to ~20k words (a 2-hour interview) in a single context window
- Must work with local Ollama models for private-data scenarios, with graceful degradation: if the selected model has a small context window, the refinement runs on the transcript in chunks of 8–10 minutes of audio each

### The `{MM:SS}` safety check

Before applying any 4.4 paragraph split proposal, code validates that the proposed split point exists as a `{MM:SS}` marker in the current paragraph. Non-matching proposals are rejected silently and logged. This is a ~5-line defensive check but it is what keeps audio sync intact through the AI pass.

### Effort estimate

Moderate. Roughly:

- AI Refinement panel UI in transcript_cleanup_dialog.py: ~150 lines
- Prompt construction and JSON parsing: ~100 lines
- Confidence marker rendering in DRAFT_3 preview and Word export: ~80 lines
- Corrections Lists backend (db tables, CRUD, import/export): ~200 lines
- Corrections Lists UI: ~250 lines
- "Add to Corrections List" button + Provisional review queue in word_editor_panel: ~100 lines
- Tests, prompts iteration, real-world tuning: material

Call it 3–4 focused development sessions for MVP, plus iteration on the prompts themselves based on real transcripts. The prompts are the longest-tail part — expect to refine them over several beta releases.

### Shipping strategy

Two sensible release increments:

**Increment 1 (earliest beta):** AI Refinement panel with 4.3 (sentences), 4.4 (paragraphs), 4.5 (speakers). Corrections Lists concept introduced with a starter UI but not yet integrated into the pipeline. User can define lists but they aren't consulted during the AI pass yet.

**Increment 2 (following beta):** Wire 4.1 (typos) and 4.2 (Corrections List) into the AI pass. Add the Provisional Corrections List mechanism and "Add to Corrections List" button in word_editor_panel. Enable live list growth during review.

This lets users start benefiting from structural AI refinement immediately, while the Corrections List side — which is the bigger product story — gets properly designed and tested without delaying the basic feature.

---

## Open questions

1. **Default AI provider for this feature.** Should we recommend a specific model as default (Gemini Flash for cheapness, Claude Sonnet for quality)? Or just use the user's currently-selected provider?

2. **What happens if the user runs the AI pass, doesn't like the result, reverts, and then runs it again with different tickboxes?** Do we cache the DRAFT_2 → intermediate results, or just re-run from scratch? Re-run is simpler; cache is more responsive for exploration. Probably re-run for MVP.

3. **Version safety:** if the transcript has already been imported and the user later wants to re-run the AI refinement pass on it, can they? Suggest yes, via a "Re-refine with AI" option in the Thread Viewer, which pulls the original DRAFT_2 from an archived copy. Low priority for MVP.

4. **Telemetry:** should we log (anonymised) statistics on how often each tickbox is used, how often users revert DRAFT_3, and how often they promote Provisional Corrections? This would inform future prompt improvements but raises privacy questions — probably leave out of MVP and revisit if real usage suggests it's needed.

---

*End of specification. Ready for second review before commitment to the roadmap.*
