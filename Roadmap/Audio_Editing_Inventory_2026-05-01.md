# Audio Editing Inventory — Pre-Packaging Review

**Date:** 1 May 2026
**Status:** Working document — starting point for the audio-editing review session of 2 May 2026
**Purpose:** A single place that captures the entire audio-transcription-and-editing chain as it stands today, so we can decide what to ship as-is, what needs polish, and what to mark explicitly as not-doing before packaging.

---

## 1. Why this document exists

Enhancement 25 (Local Voice-Based Speaker Identification) closed yesterday as not viable. With that decided, the audio-editing surface is essentially as feature-complete as it's going to be in this cycle, and packaging is the natural next step. Before packaging, we want to be clear about three things:

1. **What's there.** The full inventory of components in the audio chain.
2. **Whether a naive user can navigate it.** Walking the workflow end-to-end as if for the first time, with attention to where confusion is most likely.
3. **What to mark explicitly as not-doing.** Things we've investigated or considered and decided against, so they're not silently haunting the UI or the docs.

This document is the starting point. The session itself decides what action items fall out.

---

## 2. The chain at a glance

The audio editing chain has six stages. Status legend: ✅ shipping · 🟡 in flight (v1.7-alpha) · 🟠 needs review before shipping · ❌ explicitly not doing.

| # | Stage | Status | Notes |
|---|---|---|---|
| 1 | Source acquisition | ✅ | Local files + 10+ web/platform sources. Stable. |
| 2 | Transcription engine choice | 🟠 | Three engines work (Faster-Whisper, OpenAI Whisper, AssemblyAI) plus Moonshine (limited use). Default-engine question for Faster-Whisper (Large V3 vs Turbo) needs resolving. |
| 3 | Transcription run | ✅ | Progressive segment display, caching by hash. Stable. |
| 4 | Cleanup dialog | 🟠 | Pipeline works. Dialog has stale UI elements that should be cleaned up given #25 closure. |
| 5a | Edit in Thread Viewer | ✅ | Audio playback, sentence-level seek, paragraph editor, SpeakerPanel, AI prompts. |
| 5b | Edit in Microsoft Word | ✅ | Word + companion player + speaker panel. Three-window workflow. |
| 6 | AI processing | ✅ | Audio-linked summaries with `▶ Jump to MM:SS` links work end-to-end. |
| — | Corrections Lists + Backups | 🟡 | v1.7-alpha plan dated 28 April 2026 — in flight. Adds to Stage 4 and Stages 5a/5b. |
| — | Local voice-based speaker ID | ❌ | Investigated and closed. AssemblyAI is the production diarisation path. |
| — | AI Transcript Refinement (v3) | ❌ | On hold. May come off hold per the framing in the Voice ID Investigation log §8 — strategic call, not in this packaging cycle. |

---

## 3. End-to-end user walkthrough

Walking the chain as a first-time user. For each stage: what they do, what they see, and where confusion is most likely.

### Stage 1 — Get the audio in

**What they do.** Drag an audio file in, or paste a YouTube URL, or open the Google Drive browser, or pick from a podcast feed.

**What they see.** Progress indicator while the audio is acquired. A new entry appears in the Documents Library when it's done.

**Confusion risk.** Low. The input field is the obvious target.

### Stage 2 — Choose a transcription engine

**What they do.** First-time users hit Audio Settings to choose an engine. Returning users skip this.

**What they see.** A dropdown listing four engines: **Faster-Whisper** (local), **OpenAI Whisper** (cloud), **AssemblyAI** (cloud), **Moonshine** (local, lightweight). Each has its own configuration (model size for Faster-Whisper; API key for the cloud ones; etc.).

**Confusion risk — high, and worth attention.** Three concrete worries:

- **Which engine should they pick?** The `AUDIO_TRANSCRIPTION_GUIDE.md` document handles this beautifully — comparison table, scenario-based recommendations. But is it surfaced *at the moment of choosing*, or do they have to know to go and find it? Worth checking whether the Audio Settings dialog has a link to it or an inline summary.
- **Faster-Whisper Large V3 vs Turbo.** Turbo was added as an option in April 2026 but underperforms Large V3 on non-English audio (Vietnamese was the test case). Large V3 should remain the default. Worth checking: does the model dropdown make this clear? Anything along the lines of *"Large V3 (recommended; best for all languages)"* and *"Turbo (faster; English only)"* would help — or any wording that nudges multi-language users away from Turbo.
- **Moonshine.** Earlier testing established Moonshine is fit for short clips and dictation but not for extended transcriptions. Is the engine dropdown labelled in a way that conveys this, or could a user select it and then waste time on a 60-minute interview? Worth a quick UI check.

### Stage 3 — Run the transcription

**What they do.** Click "Transcribe Audio".

**What they see.** Text appears progressively in the source pane, segment by segment, as the engine produces it.

**Confusion risk.** Low. Progressive display is naturally reassuring.

### Stage 4 — The cleanup dialog

**What they do.** When transcription completes, the cleanup dialog opens automatically. They make choices in three sections.

**What they see today.**
- **Section A — Cleanup.** "Remove breath fragments" checkbox, "Keep listener back-channels as [annotations]" sub-checkbox.
- **Section B — Speaker identification.** Three radios: "Skip — assign manually later" (default), "Suggest speakers automatically (heuristic, provisional)", "Detect speakers by voice *(not available — see Help for setup)*".
- **Section C — Speaker names.** Two text boxes for Speaker 1 / Speaker 2 names. Hidden when Section B is on Skip; appears for the other two options.
- **Run Cleanup / Skip cleanup buttons.**
- After cleanup runs, the buttons change to **Open in: Thread Viewer / Microsoft Word**.

**Confusion risk — moderate, with concrete cleanup items now that #25 is closed:**

- **The "Detect speakers by voice (not available)" radio is now permanently misleading.** It was holding a place for a feature that is no longer coming. Three sensible options: (a) remove the radio entirely; (b) keep it but rename to "Detect speakers by voice (cloud — AssemblyAI)" with a tooltip explaining it requires AssemblyAI selection at Stage 2; or (c) remove it from the dialog and surface AssemblyAI's automatic diarisation upstream at engine-choice time. Option (c) is probably the cleanest — speaker-detection-by-voice is an engine choice, not a cleanup choice. **Worth deciding tomorrow.**
- **The word "heuristic" in "Suggest speakers automatically (heuristic, provisional)" may not parse for naive users.** Possible rewording: *"Suggest speakers automatically (rough first-pass — you'll review)"* or similar. Small but real.
- **No indication that AssemblyAI users get reliable speaker labels automatically.** A user who chose AssemblyAI at Stage 2 should probably see Section B differently — speakers are *already* assigned by AssemblyAI; Section C is just for naming them. Right now Section B presents the same three options to all users regardless of engine.

### Stage 5 — The routing choice (Thread Viewer vs Word)

**What they do.** Click one of the two buttons.

**What they see.** Either Thread Viewer opens (Stage 5a) or Word + companion player + speaker panel open together (Stage 5b).

**Confusion risk — moderate.**

- **The two routes look like a binary quality decision but they aren't.** They're two equivalent editing environments suited to different working styles. Is that conveyed? A brief tooltip on each button would help — e.g. Thread Viewer: *"Edit and analyse inside DocAnalyser"*, Word: *"Edit in Word with audio side-by-side; ideal for long-form structural editing"*.
- **Naive users may not know that picking one doesn't lock them out of the other.** They can come back and route differently. Worth checking whether that's discoverable.

### Stage 5a — Editing in Thread Viewer

**What they do.** Read the transcript. Click sentences to seek the audio. Edit in place. Use the SpeakerPanel for speaker assignment.

**What they see.** Paragraphs with grey `[MM:SS]` headers, bold speaker labels, sentence-level click-to-seek. Audio Playback control bar across the top. Edit / Save toggle. Merge / Split buttons. Speaker filter dropdown.

**Affordances available today:**
- ✅ Sentence-level click-to-seek
- ✅ Inline word correction (✏ → edit → 💾)
- ✅ Paragraph splits (Enter or ✂)
- ✅ Paragraph merges (⊕)
- ✅ Per-paragraph speaker rename
- ✅ SpeakerPanel: bulk click-driven speaker assignment with audio playback per paragraph
- ✅ Run AI prompts inline
- ✅ Audio-linked AI summaries (`▶ Jump to MM:SS` links)
- 🟡 *Coming in v1.7-alpha:* "Add to Corrections List" button on the toolbar — promotes a found-and-fixed mistranscription into a list that applies automatically on future cleanup runs
- 🟡 *Coming in v1.7-alpha:* Backups dialog — restore the transcript to any previous state (auto-snapshots after cleanup, AI runs, save events; manual snapshots on demand)

**Confusion risk.** Low for the reading and seeking. Moderate for the edit-mode toggle (✏ / 💾) — the mental model that you must enter edit mode before splits/merges work isn't always obvious. Worth a quick check whether the disabled state of split/merge buttons is visually clear when not in edit mode.

**Known small gap.** Bulk rename of all paragraphs sharing a speaker label (e.g. all `SPEAKER_A` to `Glenn Diesen` in one click). Currently per-paragraph only. Probably not worth fixing for this packaging cycle — workaround is the cleanup dialog Section C *or* the Find/Replace path in Word — but worth knowing.

### Stage 5b — Editing in Microsoft Word

**What they do.** Read in Word, listen in companion player, assign speakers via the always-on-top SpeakerPanel which polls Word's COM cursor.

**What they see.** Three windows open simultaneously:
- **Word** — the transcript as `.docx` formatted as `[MM:SS]  **Speaker:**  text`. Title heading, Document Information block at the top, usage note about preserving timestamps.
- **Companion player** — small window with playback controls, draggable slider, "Jump to MM:SS" text field.
- **Speaker Panel** — non-modal always-on-top panel, polls Word's COM cursor every 500 ms, badge shows `● Word linked` / `○ Word not linked`.

**Affordances available today:**
- ✅ Per-paragraph speaker assignment by clicking name buttons in the panel
- ✅ Bulk substitution of speaker IDs to real names ("Apply names")
- ✅ Free-form structural editing in Word (splits via blank lines, merges by deleting line breaks, free text edits)
- ✅ "Refresh ¶" to re-sync after structural edits
- ✅ "Save to DocAnalyser" — parses the `.docx` back into entries, preserves `[MM:SS]` anchors
- 🟡 *Coming in v1.7-alpha:* "Add to Corrections List" button (matches the Thread Viewer button — same shared dialog)
- 🟡 *Coming in v1.7-alpha:* Backups dialog accessible from this panel too

**Confusion risk — moderate-to-high. This is the route most likely to need its own quick-start.**

- **Three-window choreography is non-obvious.** A naive user may not realise the SpeakerPanel needs to stay open, or that clicking in Word is what drives it. Worth confirming there's a clear intro message on first launch — even a one-shot "Welcome to Word editing — here's how the three windows work together" overlay would help.
- **`[MM:SS]` tokens look like decoration but are load-bearing.** Word's usage note mentions this, but a user who doesn't read it might delete them and break Save-to-DocAnalyser. Worth verifying the failure mode is graceful when a token is missing.
- **The `● Word linked` / `○ Word not linked` badge.** A naive user may not know what to do when it goes red. Tooltip-on-hover with a one-line action ("Click into the Word document") would help.

### Stage 6 — AI processing

**What they do.** With the cleaned transcript loaded, select a prompt from the Prompts Library and click Run.

**What they see.** AI response appears in the Thread Viewer. Audio-linked summaries render `[SOURCE: "..."]` markers as clickable `▶ Jump to MM:SS` links.

**Confusion risk.** Low for users already familiar with the Prompts Library. The audio-linked summary feature is the killer feature here — worth checking that there's a curated default prompt visible to first-time users that demonstrates it (named something like "Audio-Linked Summary" so its purpose is obvious).

---

## 4. What's in flight (v1.7-alpha)

Two features, ten work items, ~2 calendar weeks. Plan dated 28 April 2026. Both directly improve the audio-editing experience.

**Corrections Lists.** A list of project-scoped find/replace pairs (e.g. *"Glen Deesen"* → *"Glenn Diesen"*) that grow over time as the user processes more audio in a domain. Applied automatically during cleanup. Three integration points:
- Cleanup dialog Section A gains a `Apply corrections from list: [None ▾] [Edit lists…]` row.
- Settings → Corrections Lists management UI for creating, editing, importing, exporting lists.
- "Add to Corrections List" buttons in Thread Viewer and Word Speaker Panel — promote a one-off fix into a permanent list entry.

**Backups.** Auto-snapshots of the transcript at four trigger points (post-cleanup, post-AI-refinement-stub, at-import, session-start in Word) plus on-demand manual snapshots. Backups dialog accessible from both editing environments lets the user preview, revert, or delete.

**Implication for tomorrow's review.** v1.7-alpha is the natural last feature batch before packaging. Two questions worth deciding:

1. Does packaging wait for v1.7-alpha to ship, or do we package what we have today (v1.6-ish) and treat v1.7-alpha as the next release? The v1.7-alpha plan was framed around a PhD researcher's near-term needs — that timing constraint may push the answer one way or the other.
2. If packaging waits for v1.7-alpha, the "Add to Corrections List" buttons in §5a and §5b above move from 🟡 to ✅ in this inventory. Worth re-doing the workflow walkthrough for those two stages in tomorrow's session if so.

---

## 5. What's been investigated and closed

**Local voice-based speaker identification (Enhancement 25).** Closed 1 May 2026 after the segmentation test plan dated 27 April 2026 produced a definitive negative. Lightweight ONNX speaker-embedding models (CAM++, eres2net via sherpa-onnx) cannot discriminate same-gender English speakers reliably enough for production use; pyannote-audio (and its ONNX surrogate) does not run within the hardware envelope. **AssemblyAI remains the production diarisation path.** See `Voice_ID_Investigation_2026-05-01.md`.

**Documentation cleanup that follows from this:**
- `AUDIO_TRANSCRIPTION_GUIDE.md` "Level 3 — Voice Recognition (Future Feature)" section refers to pyannote.audio as a coming feature. **Now stale — needs rewriting** to reflect that local voice-ID is not coming and that AssemblyAI is the speaker-ID path for users who need automatic and reliable assignment.
- `transcript_cleanup_dialog.py` `PYANNOTE_ENABLED = False` flag and the disabled "Detect speakers by voice" radio — see Stage 4 above.
- `03_DOCUMENT_PROCESSING.md` describes `diarization_handler.py` as "complete and retained for future use, currently disabled". This wording should change to *"decommissioned — retained in the codebase only for reference; pyannote-audio is not a viable local-diarisation path on the target hardware envelope"*.

These are small documentation/UI cleanups but they're material for the naive-user goal — having the UI advertise an unavailable feature creates exactly the confusion we're trying to avoid.

---

## 6. What's parked (v3 AI Transcript Refinement)

Spec at `Documentation/AI_Transcript_Refinement_Spec_v2.md` (the v2 file is the most recent shipped version of the spec — v3 was the in-progress revision before being put on hold). On hold since 27 April 2026 due to the cloud-vs-privacy contradiction.

**The framing has changed.** Per the Voice ID Investigation log §8: users who want diarisation already accept the cloud path via AssemblyAI; AI refinement features inherit the same trade-off cleanly without compounding the privacy cost. So v3 *can* come off hold with that framing, if Ian decides.

**Strategic call, not in scope for this packaging cycle.** Worth a one-line decision tomorrow ("park v3 until after packaging" vs "schedule v3 for v1.8"), but no action items either way.

---

## 7. Open questions for tomorrow

The questions clustered by where they bite in the workflow, in roughly the order they'd come up.

**Stage 2 (engine choice):**
1. Is `AUDIO_TRANSCRIPTION_GUIDE.md` surfaced at the moment a user picks an engine, or do they have to know to go find it?
2. Faster-Whisper model dropdown — does it make Large V3 vs Turbo trade-off clear?
3. Is Moonshine adequately labelled for its narrow use case (short clips), or could a naive user pick it for a 60-min interview?

**Stage 4 (cleanup dialog):**
4. **Decision:** what to do with the now-permanently-misleading "Detect speakers by voice (not available)" radio — remove, rename, or move upstream?
5. Reword "heuristic" in Section B?
6. Should Section B present differently to AssemblyAI users (since AssemblyAI handles speaker ID upstream)?

**Stage 5 (routing + editing):**
7. Tooltips on the Thread Viewer / Word buttons explaining the choice?
8. Is there a first-launch overlay for the Word three-window workflow? If not, is that worth adding?
9. Word path: confirm graceful failure when `[MM:SS]` token is deleted by the user.

**Cross-cutting:**
10. Does packaging wait for v1.7-alpha, or ship now and treat v1.7-alpha as the next release?
11. Strategic call on v3 (park or schedule).
12. Documentation cleanup pass: AUDIO_TRANSCRIPTION_GUIDE.md, 03_DOCUMENT_PROCESSING.md, transcript_cleanup_dialog.py UI text — all carry stale references to local voice-ID.

---

## 8. Suggested order of attack tomorrow

A pragmatic sequence:

1. **Walk the workflow together** — Stages 1 → 6, screen by screen if helpful, identifying anything in §3 that doesn't match the actual UI right now. That validates this inventory and surfaces anything I've described from documentation rather than from the running app.
2. **Resolve the small UI cleanups** that fall out of #25's closure — the disabled radio, the "Future Feature" note in the user guide. These are quick and remove confusion.
3. **Decide the packaging-vs-v1.7-alpha question** — this gates everything else.
4. **Decide the polish-item cuts** — items 1, 2, 3, 5, 6, 7, 8, 9 from §7 above. Some will be quick fixes, some will be "not in this cycle, document and move on".
5. **Strategic v3 decision** — park or schedule.
6. **Action list out** — anything that survived all of the above as a "do this before packaging" item.

Should be 1–2 hours all up, depending on how much real-UI inspection we do at step 1.

---

*Inventory drafted by Claude on 1 May 2026, ahead of the audio-editing review session of 2 May 2026. Sources: `Roadmap/Audio_Workflow_End_to_End_2026-04-28.md`, `Roadmap/v1.7-alpha_Implementation_Plan_2026-04-28.md`, `Roadmap/Voice_ID_Investigation_2026-05-01.md`, `AUDIO_TRANSCRIPTION_GUIDE.md`, `Documentation/ProjectMap/03_DOCUMENT_PROCESSING.md`, `Documentation/ProjectMap/05_UI_DIALOGS_CONVERSATION.md` (header overview), `Documentation/ProjectMap/14_ROADMAP_STATUS.md`.*
