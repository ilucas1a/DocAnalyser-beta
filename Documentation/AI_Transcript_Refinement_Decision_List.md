# AI Transcript Refinement Spec — Consolidated Decision List

**Prepared:** 22 April 2026
**Status:** Awaiting user decisions before v3 consolidation
**Context:** This list captures every open question, provisional answer, and flagged option from our point-by-point review of the v2 spec. Work through each item and confirm, adjust, or defer. Once these decisions are locked, v3 will be produced incorporating all agreed refinements plus these locked-in choices.

Items are grouped by theme rather than strict order of discussion, so related decisions appear together. Each carries its provisional answer (where one exists) and a short rationale. The "Your decision" column is for you to fill in.

---

## A. User education and first-time experience

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| A1 | When a naive user expands the AI Refinement panel for the first time, should they see a one-off expansive explanation (first-run-wizard style) in addition to the inline caption? | Yes — a short "What this does" dialog on first expansion, with a "don't show again" option. | |
| A2 | Should F1 context help on the collapsed AI Refinement panel header provide additional tooltip-style explanation? | Yes — consistent with existing F1 help system across DocAnalyser. | |
| A3 | Exact wording of the step 7 warning message (AI refinement applied, hover for details, colour legend). | Draft wording written in point 28; ready for review. | |

## B. Corrections Lists — structure and defaults

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| B1 | Ship with a pre-created "General" Corrections List as a default target? | Yes — reduces first-use friction; users can ignore if they prefer project-scoped lists. | |
| B2 | Step 3.1 dropdown behaviour: enabled regardless of tickbox state (Option A), or only enabled when tickbox ticked (Option B)? | Option A — dropdown always enabled, users can create/browse without committing to apply. | |
| B3 | Corrections Lists MVP matching rules: simple find-and-replace with case-sensitivity and word-boundary options? | Yes — defer context-aware matching to v2. | |
| B4 | Corrections List entries support multi-word phrases, not just single words (Gulargambone case)? | Yes — entries are arbitrary text-to-text substitutions with longest-match-wins semantics. | |

## C. Provisional Corrections List — review and editing

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| C1 | Apply Provisional Corrections retroactively to produce a clean DRAFT_3 (no residual provisional markers on import), or forward-only? | Retroactively — cleaner result, matches user's mental model of "this was always supposed to be a correction." | |
| C2 | The Provisional review panel allows the user to edit the AI's suggested replacement before accepting or promoting (Gulargambone vs Guloggambone). | Confirmed — editable text field pre-filled with AI proposal. | |
| C3 | Capture original AI proposal alongside user's final edit, for diagnostic purposes? | Yes, backend-only — not surfaced in UI for MVP. | |
| C4 | Show surrounding context ("Show context") per provisional correction during review? | Yes — expandable row showing the paragraph the phrase appears in, with the phrase highlighted. | |
| C5 | Multi-occurrence corrections: user's edit applies to all occurrences uniformly. Edge case (same phrase → different corrections in different places) handled via dismiss-and-manual. | Yes — uniform for MVP; defer per-occurrence support. | |

## D. Speaker assignment

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| D1 | Default pre-populated role names in speaker assignment. | "Speaker 1" and "Speaker 2" — neutral, broadly applicable. | |
| D2 | Role field per speaker: optional, free-text input with autocomplete suggestions from common roles? | Yes — free-text, not a fixed dropdown. | |
| D3 | Role field character limit. | 50 characters. | |
| D4 | Speaker name assignment (3.2) available independently of AI refinement (4.5)? | Yes — 3.2 is a simple substitution pass; 4.5 adds AI re-attribution on top. | |

## E. AI Refinement — behaviour and provider

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| E1 | Default AI provider for refinement operations. | User's currently-selected provider (same as other text operations). | |
| E2 | Cache intermediate results on re-run (user reverts, runs again with different tickboxes)? | No — re-run from scratch for MVP. | |
| E3 | Support "Re-refine with AI" from Thread Viewer for already-imported transcripts? | Yes, low priority for MVP. | |
| E4 | Anonymised telemetry on tickbox usage, revert frequency, Provisional promotion rates? | No — leave out of MVP. | |
| E5 | Local AI (Ollama) supported as a provider for refinement? | Yes — honest caveats about quality gap per capability; no hard restrictions. | |
| E6 | Cost preview shows "Free (local)" with quality caveat when Ollama selected? | Yes. | |
| E7 | Recommend a specific Ollama model in the dialog, or generic "results may vary by model size" note? | Generic note — the ecosystem evolves quickly and hardcoded recommendations go stale. | |

## F. Confidence markers — behaviour

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| F1 | Every AI change gets a visible marker (including high-confidence), not silent application. | Yes — confirmed in point 17. | |
| F2 | Colour scheme: green (high) / amber (medium) / red (low) / blue (Provisional Corrections). | Green/amber/red/blue confirmed in principle; final confirmation of exact colours. | |
| F3 | Markers are dots placed before affected content (paragraph / sentence / word or phrase). | Yes — confirmed. | |
| F4 | Every dot carries an attached Word Comment with structured content (capability, change description, confidence level). | Yes — confirmed in point 17. | |
| F5 | Comments shown on hover (or click), not in margin pane by default. | Yes — confirmed in point 18. | |
| F6 | Filter controls in word_editor_panel ("show only amber and red," "hide green"). | Yes — included in MVP. | |
| F7 | "Bulk-accept all green" button in word_editor_panel. | Yes — included in MVP. | |
| F8 | When user edits text with an AI marker, marker stays by default and comment updates to reflect the edit chain. | Yes — provenance preserved by default. | |
| F9 | Tracked Changes mode as an advanced option from the AI Refinement panel. | Defer beyond MVP — core feature is dots + comments; Tracked Changes mode can be added if demand emerges. | |

## G. Confidence markers — safety and persistence

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| G1 | `{MM:SS}` safety check behaviour: when AI proposes a paragraph split that doesn't align with a sentence timestamp, surface visibly (Option C). | Option C confirmed at point 37. | |
| G2 | Mode 2 ("Finalise"): markers hidden via Word's hidden-text formatting, retrievable via "Show AI markers" button in word_editor_panel. | Yes — confirmed at point 20. | |
| G3 | Mode 3 ("Export publication copy"): produces a new file with markers and AI comments physically stripped, working copy unchanged. | Yes — confirmed at point 21. | |
| G4 | Mode 3 export dialog: checkbox "Remove all comments (including your own editing notes)", default ticked. | Yes — confirmed at point 22. | |
| G5 | Mode 3 export dialog: checkbox "Remove document metadata (author name, file paths, edit history)", default ticked. | Yes — Word's Inspect Document mechanism. | |
| G6 | Mode 3 export dialog: checkbox "Include timestamps [MM:SS]", default unticked. | Yes — publication copies usually don't want internal timing anchors. | |
| G7 | Filename suggestion for publication copy. | `[Transcript_Title]_Final.docx` or similar. Needs confirmation of preferred format. | |

## H. Sync and snapshots

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| H1 | "Stay in sync" principle: working document and stored transcript never diverge; auto-save fires on boundary actions. | Yes — confirmed at point 25. | |
| H2 | Auto-save trigger: continuous (every edit) or on boundary actions (export, close, AI operations)? | Boundary actions — batches writes, avoids database churn. | |
| H3 | Visible sync status indicator in word_editor_panel ("In sync" / "Unsaved changes"). | Yes — included in MVP. | |
| H4 | Automatic snapshot triggers: post-heuristic-cleanup, post-AI-refinement, at-import, session-start in Word. | Yes — confirmed at point 28. | |
| H5 | Manual "Create snapshot" button in word_editor_panel with optional user-supplied label. | Yes — included in MVP. | |
| H6 | Manual snapshot labels: optional (empty label allowed), not required. | Yes. | |
| H7 | Snapshots UI: list dialog accessed from word_editor_panel and Thread Viewer. | Yes — confirmed at point 27. | |
| H8 | Snapshot actions: Preview (read-only), Revert (with auto-snapshot of current state first), Delete (with confirmation). | Yes — confirmed at point 27. | |
| H9 | Snapshot retention policy for MVP: keep all until transcript deleted (no aged-out thinning). | Yes — storage is negligible; revisit only if needed. | |
| H10 | Undo-the-revert via standard Ctrl+Z. | Defer beyond MVP — explicit revert-the-revert gives same result. | |
| H11 | Reverting to a pre-finalise snapshot will make AI markers visible again (reflecting the snapshot's state at that moment). | Yes — correct behaviour; noted in spec. | |

## I. Delivery and increments

| # | Question | Provisional answer | Your decision |
|---|---|---|---|
| I1 | Ship the feature in two increments: Increment 1 = structural AI refinement + Corrections List UI but not yet integrated into the pipeline; Increment 2 = Corrections List pipeline integration + Provisional Corrections + live list growth. | Two-increment strategy confirmed in v2; needs confirmation it still makes sense given the shape v3 has taken. | |
| I2 | Alternative: ship all capabilities together as a single MVP release, given the close integration of the pieces. | Possible alternative — the Corrections List integration is now tightly woven through the spec; splitting may produce awkward intermediate states. | |

---

## Summary of decisions needed

**Quick-resolution items (probably just confirm):** A1, A2, B1, B2, B3, B4, C1, C2, C3, C4, C5, D1, D2, D4, E1, E2, E3, E4, E5, E6, E7, F1, F2, F3, F4, F5, F6, F7, F8, F9, G1, G2, G3, G4, G5, G6, H1, H2, H3, H4, H5, H6, H7, H8, H9, H10, H11

**Items needing actual choice or input:** A3 (review the warning wording), D3 (confirm 50-char limit or specify different), G7 (confirm filename format), I1/I2 (single- vs two-increment delivery)

Work through the list at whatever pace suits. Confirm with "yes" for items where the provisional answer stands, or provide an alternative where it doesn't. Once the list is complete, v3 will be produced as a single consolidated document with all decisions folded in, ready to become the specification that development works from.
