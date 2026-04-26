# 14 - Roadmap Status (Review of 21 April 2026)

## Overview
A review of the v2.0 roadmap (January 2026) was conducted on 21 April 2026 and substantially expanded with new enhancements identified during review. This file captures the status snapshot and revised phasing — pick-up notes for the next planning session.

**Source document:** `Roadmap/DocAnalyser_Roadmap_Review_Updated_21_April_2026.docx`

> **Headline:** Of the 11 original enhancements, **8 complete, 1 partial, 2 outstanding**. **13 new enhancements (12–24)** added during review — most planned, two already complete (14 Help Text Editor, 22 Google Drive sub-item).

---

## Status Snapshot

### Original enhancements (1–11)

| # | Name | Status | Notes |
|---|------|--------|-------|
| 1 | Prompt Import/Export | **Complete** | `import_export.py` (Mar 2026), .docanalyser ZIP. Document export added Apr 2026. |
| 2 | Web Response Import | **Complete** | "Via Web" + Web Response Banner + clipboard capture |
| 3 | Tree Structure for Libraries | **Complete** | Both libraries, 4 levels (exceeds spec's 3) |
| 4 | Multi-Document Collection Analysis | **Complete** | Combine vs. Process Separately |
| 5 | **Content Subscriptions & Auto-Processing** | **Partial** | Manual Check Now works (Apr 2026). **Outstanding: scheduling, "What's New" dashboard, bug shakedown.** Flagship differentiator. |
| 6 | AssemblyAI + Speaker Diarization | **Complete** | Third transcription engine |
| 7 | Multi-Model Peer Review | **Outstanding** | Niche; defer to Phase C |
| 8 | Zotero Integration | **Outstanding** | Value depends on academic-user share |
| 9 | Research Mode / RAG | **Superseded** | `semantic_search.py` foundation only. **Superseded by Enhancement 23 (Research Agent).** |
| 10 | Unified Viewer Multi-Source Display | **Complete** | Collapsible per-source sections in thread viewer |
| 11 | Podcast RSS Support | **Complete** | `podcast_handler.py` + browser dialog |

### New enhancements (12–24, added during review)

| # | Name | Status | Phase |
|---|------|--------|-------|
| 12a | GitHub-Hosted Model Lists | Planned | A |
| 12b | OpenAI-Compatible Generic Provider | Planned | B |
| 13 | Workspaces | Planned (foundation in place — `workspace_id` pre-wired in folders, cost_log tables) | B/C |
| 14 | Help Text Editor | **Complete** — `maintenance/help_text_editor.py` | A |
| 15 | User-Facing Message Editor | Planned — centralise hardcoded strings into `messages.json` / SQLite | A |
| 16 | Settings Registry | Planned — central settings table + read-only viewer | A |
| 17 | Module Dependency Map | Planned — `maintenance/dependency_map.py`, ~60–80 lines | A |
| 18 | Pre-Release Smoke Test | Planned — runs before installer build | A |
| 19 | Config/Constants Audit Tool | Planned — one-off scan for magic numbers | A |
| 20 | Function-Level Documentation Pass | Planned — incremental, prioritise complex modules | A |
| 21 | Shareable Audio-Linked Review Package | Planned — `listen.html` + `corrections.docx` + audio ZIP for interviewee review (zero-install) | B |
| 22 | Google APIs Integration | **Partial** — Drive complete; Docs export, Gmail, Calendar, Cloud Speech all planned | B/C |
| 23 | Research Agent — Corpus Query Mode | Planned — RAG via existing `semantic_search.py`. Supersedes #9. | B |
| 24 | Faster Whisper Large V3 Turbo | Planned — recommended local default (~1.6 GB, ~4× faster than Large V3) | A |
| (25) | Map Integration | Planned — tkintermapview, geocoding, clickable pins. 3–5 weeks. | C |

> ⚠️ The source doc reuses **#23** for both Research Agent and Map Integration. Treat Map Integration as **#25** going forward to disambiguate.

---

## Revised Phasing

The original v2.0 five-phase structure is obsolete (Phases 1–3 effectively complete). New three-phase structure:

### Phase A — Quick Wins (days each)
**12a** (GitHub model lists), **24** (Faster Whisper Turbo), **15** (Message Editor), **16** (Settings Registry), **17** (Dependency Map), **18** (Smoke Test — best built after 14/15/16), **19** (Constants Audit), **20** (Function Docs — incremental)

Phase A is mostly developer-tooling and maintenance plumbing — high day-to-day value, low individual effort. **#14 already done.**

### Phase B — Differentiating Features (weeks)
1. **#5 Content Subscriptions completion** — scheduling + "What's New" dashboard + shakedown. **The flagship differentiator.**
2. **#23 Research Agent (Corpus Query Mode)** — natural-language queries across the document library, cited answers. Builds on `semantic_search.py`. Primary audience: oral historians.
3. **#21 Audio-Linked Review Package** — interviewee verification workflow.
4. **#22 (subset)** — Google Docs export, Gmail for Review Package distribution.
5. **#12b** Generic OpenAI-Compatible provider — extensibility before wider release.

### Phase C — Power User Features (weeks–months)
**#7** (Multi-Model Peer Review), **#8** (Zotero — only if academic audience), **#13** (Workspaces), **#22 (rest)** (Calendar, Cloud Speech on demand), **#25** (Map Integration, 3–5 weeks), Deepgram transcription engine (optional).

---

## Roadmap Corrections (v2.0 doc → current reality)

| Item | v2.0 said | Now |
|------|-----------|-----|
| Local AI provider | LM Studio | Ollama with setup wizard |
| AI providers count | 5 cloud | 6 cloud + 1 local |
| Content sources | No CSV/XLSX/Substack | All supported |
| Dictation | Not mentioned | Fully implemented |
| Standalone Conversations | Not mentioned | Fully implemented |
| Installer bundling | Not mentioned | Tesseract, Poppler, FFmpeg bundled |
| Tree structure depth | "Cap at 3 levels" | 4 levels |
| Enhancement 10 | "Proposed" | Already built and working |
| Storage backend | JSON flat files | SQLite (JSON retained as backup) |

---

## Built but Not in the v2.0 Roadmap

Ollama Local AI · Dictation/Speech-to-Text · Standalone Conversations · First-Run Wizard · F1 Context Help System · GitHub Update Checker · Cost Tracking · Smart OCR Caching · Substack Support · Spreadsheet Support (CSV/XLSX) · Multi-platform video support · Bundled Installer Tools · Branch/Conversation Management · Auto-Save Responses · Curated Default Prompts · **SQLite Database Migration** (full migration from JSON)

---

## Strategic Question (Open)

The Tkinter architecture is becoming awkward for features that need background scheduling and dashboard UIs — notably Enhancement 5 (Content Subscriptions). Worth revisiting whether to push through the remaining roadmap on Tkinter, or whether the cumulative awkwardness justifies starting the **Clarity AI** successor rewrite. Not a current priority — captured here so it doesn't get lost.

---

## Recommended Immediate Path

The highest-impact development sequence:

> ~~Prompt Import/Export~~ ✓ → ~~GitHub Model Lists~~ (Phase A pending) → ~~Podcast RSS~~ ✓ → **Content Subscriptions completion** → Generic Provider

**Next concrete priority** (after the in-progress audio transcription editing upgrade): finish Enhancement 5 — scheduling layer, "What's New" dashboard, and shakedown of the existing implementation.

---

## Polish Items (small UX fixes — slot into Phase A)

These are small UX improvements identified while shaking down the Subscriptions feature. They don't justify standalone enhancement numbers but are worth capturing before they're forgotten. Each is a ~1–3 hour change at most, except P6 which is a migration constraint and P7 which is a real bug fix.

### P1 — Digest status bar should identify itself

**Problem:** During a digest run the status bar shows bare strings like *"Processing chunk 1/9…"* and *"Consolidating 9 chunk results…"*. These are indistinguishable from the per-item Check Now status messages, and give the user no way to tell that the digest is actually running on fresh content rather than re-running on stale inputs.

**Fix:** Prefix all status messages emitted by `generate_digest()` with run context, e.g.:

> `Generating digest from 6 sources [tiered briefing v2] — Processing chunk 1/9…`

The "from N sources" prefix doubles as an early warning for the bug we hit on 25 April 2026: if the prefix says "from 2 sources" the user instantly knows Check All hasn't run yet, before waiting through 15 minutes of AI processing for a stale digest.

**Where:** `subscription_manager.generate_digest()` — wrap the existing `_log()` calls so every status message gets the prefix. Look for the `status_cb` callback path.

**Effort:** Trivial — one helper, ~10 lines.

### P2 — Per-subscription Check Now status bar should name the subscription

**Problem:** During a Check All, the status bar shows *"Processing chunk 1/3…"* with no indication of which subscription is being processed. The persistent "Now checking [N/M]: <n>" banner gives the subscription name, but the chunk progress on the main status bar drops it.

**Fix:** Pass the subscription name through to the status bar so the user sees, for example:

> `Glenn Diesen — Processing chunk 1/3 of "Jeffrey Sachs: Trump's Defeat in Iran…"`

This is *easier* than P1 because each chunk genuinely maps to a single document. The log already prefixes every line with `[Subscription name]` — just propagate that to the dialog status path.

**Where:** `subscription_manager._run_ai_and_save()` — the `log()` callback already carries the subscription context; pass the document title and subscription name into the chunk-progress messages it emits.

**Effort:** Small — already-available context just needs threading through one more call site.

### P3 — Pre-flight source date display before AI runs

**Problem:** `generate_digest()` collects source ai_responses, then immediately starts the (slow, costly) AI chunking step. If the sources are stale — as on 25 April when the digest was built from 23 April content — the user only finds out by reading the output 15 minutes later.

**Fix:** Between `get_recent_responses()` and the AI call, emit a status block listing each source with its `created_at` date, e.g.:

> Found 6 source summaries:
>   • Alexander Mercouris (2026-04-25 11:26)
>   • Judge Napolitano (2026-04-25 11:38)
>   • Glenn Diesen (2026-04-25 11:40)
>   • Danny Haiphong (2026-04-25 11:45)
>   • Daniel Davis (2026-04-25 12:05)
>   • Nima — Dialogue Works (2026-04-25 12:21)
> Running AI…

A user spotting "(2026-04-23 ...)" entries in that list can cancel before the AI run starts and run Check All first, instead of discovering the staleness after the fact.

**Where:** `subscription_manager.generate_digest()` — add a status block right after the `responses = get_recent_responses(...)` call.

**Effort:** Small — one loop emitting status messages.

### P4 — Stale-source warning before generating digest

**Problem:** A natural extension of P3. Even with the date list visible, a user in a hurry will click through and run the digest on stale content. Worth a soft guardrail.

**Fix:** When the most recent ai_response among all selected subscriptions is older than (say) 12 hours, show a dialog:

> *"The most recent source summary is from 2026-04-24 11:16 — over 24 hours old. Run Check All Now first to refresh sources, or proceed anyway?"* [Cancel] [Proceed]

Threshold should probably be configurable (Settings → Subscriptions). Default of 12h means: a daily 3 am digest never trips it, but a user manually running mid-afternoon after forgetting to do Check All will be caught.

**Where:** `subscription_dialog.DigestDialog._run_digest()` — between the prompt validation and the worker thread launch, do a quick `get_recent_responses()` lookup just for the dates, and gate on the result.

**Effort:** Small — depends on whether the threshold is hardcoded or settings-backed.

### P5 — Distinct digest titles when prompt name is unchanged

**Problem:** Re-running the digest produces a doc titled `<prompt name>: <date>`. If the user runs two digests on the same day with the same prompt — which happens during shakedown — both docs share the exact same title in the library. The internal `source` string differs (so the doc IDs are unique) but the visible titles collide.

**Fix:** Append a time component when a digest with the same `<prompt name>: <date>` title already exists in the library. e.g. `Daily digest - tiered briefing v2: 25 Apr 2026 (13:55)`.

**Where:** `subscription_manager.generate_digest()` — title-construction block near the end. Optional: only add the time suffix if a prior digest with the same date+prompt-name already exists, to keep clean titles for the common case.

**Effort:** Trivial — one library lookup and a conditional time-suffix.

### P6 — Subscription list must survive any future redesign

**Problem:** Enhancement 5 (Subscriptions completion) will likely involve a tree-structure UI rework — folders/categories of subscriptions, mirroring what was done for the Documents and Prompts libraries. There is a real risk that an early-state spec involves "wipe the list and re-enter" rather than "migrate the existing data into the new structure". By 26 April 2026 the list contains **18 carefully curated subscriptions**, several with non-default settings (min_duration overrides, custom prompts) — re-entering this from scratch would be tedious and error-prone.

**Constraint for the Enhancement 5 spec:** Whatever schema change accompanies the tree-structure redesign, it must include a migration path that preserves existing subscriptions automatically. New top-level folders ("Daily geopolitics", "Long-form", etc.) can default to a single "Imported" or "Uncategorised" folder for the first launch, with the user re-organising thereafter.

**Reference:** A point-in-time snapshot of the curated list is preserved at `Roadmap/subscriptions_snapshot_2026-04-26.md` (human-readable summary) and `Roadmap/subscriptions_snapshot_2026-04-26.json` (raw JSON for faithful restore). Keep these in sync if the list materially changes before Enhancement 5 work begins — or take a fresh snapshot at the start of that work.

**Effort:** Constraint, not a fix — the cost is built into Enhancement 5's design rather than a separate task.

### P7 — Docx export emits raw markdown anchor syntax + Drive delivery should be Google Doc, not PDF

**Two related issues, one fix path.**

**Problem 7a (real bug):** When the digest doc is exported as `.docx`, internal anchor links arrive in the file as **literal markdown source text** rather than as Word hyperlink fields. Observed 26 April 2026: a digest opened from Drive as a Google Doc displayed strings like `[[Detail](#point-1)]`, `[here](#sources)`, and `Key Points {#key-points}` as plain text. The PDF export of the same digest, viewed standalone, has working clickable links — so the markdown-to-rich-text conversion exists somewhere in the codebase but is **not being applied on the docx export path**.

The user-visible consequence is that the docx (and any Google Doc converted from it) is not navigable — you can't jump from a Key Point to its detail block, can't return via [Back], can't reach the Sources list via [here]. For a long tiered-briefing digest this destroys the whole reason for the tiered structure.

**Problem 7b (delivery format):** Independently, the original plan to upload digests to Drive as PDFs runs into Drive Preview's well-documented partial support for intra-document hyperlinks — internal anchors silently fail to navigate even in correct PDFs. Confirmed via PDF Association reporting (July 2025): "the PDF feature enabling intra-document hyperlinks (PDF Link annotations) is only partially implemented in Google's Preview". This affects PDFs created by Google Docs itself — i.e. it's not a DocAnalyser problem, it's a Drive viewer limitation.

The right delivery format for Drive-hosted digests is therefore a **native Google Doc**, not a PDF. Google Docs renders all link types correctly in the Drive UI without preview limitations.

**Fix path (sequential):**

1. **Fix the docx export** so that markdown anchor syntax (`[label](#anchor)`, `{#anchor}` heading IDs, `[label](https://…)` external links) is converted into proper Word hyperlink fields and bookmark targets. This is a prerequisite for everything downstream, and also makes manually-exported docx files useful in their own right.
2. **For the 3 am digest automation:** upload to Drive as `.docx` with conversion-on-upload enabled (`mimeType: application/vnd.google-apps.document` in the Drive API call) so the result is a native Google Doc. Once 7a is fixed, the conversion preserves all hyperlinks.
3. **Optional:** keep the PDF as a sibling archival copy. The Google Doc is the navigable copy; the PDF is the immutable record.

**Where:**
- Docx export pipeline — investigation needed. The PDF path produces correct hyperlinks, so there's a working markdown-to-rich-text converter somewhere; the docx exporter either bypasses it or has its own incomplete copy. Likely starting points: search for `python-docx` usage and the digest's "save as docx" code path. The thread viewer's markdown rendering (`thread_viewer_markdown.py`) handles anchors correctly for display but is a separate code path from file export.
- Drive upload code — already exists in `google_drive_handler.py`; needs a conversion-on-upload mode added (or a separate code path for the digest automation).

**Effort:** Medium for 7a (real bug, code investigation needed, test with various link types). Small for 7b once 7a is done (one extra parameter on the Drive upload call).

**Immediate workaround until fixed:** Use the PDF export, opened standalone or via "Open with → Browser" from Drive. The PDF route already works correctly for everything except Drive Preview itself.

### P8 — Digest decoupled from soft-delete state (FIXED 26 April 2026)

**Status:** Code fix applied to `subscription_manager.get_recent_responses`. Pending verification on next DocAnalyser restart.

**Symptom (before fix):** `Generate Digest` produced near-empty output (commonly 2 sources of an expected 10) even when ai_responses for most subscriptions clearly existed in the database. Pattern was consistent across multiple days. Worked correctly only for whichever subscriptions had been processed in the last hour or two.

**Root cause:** `get_recent_responses` was reading the documents table via `db.db_get_all_documents()`, which silently filters `WHERE is_deleted = 0`. The user routinely cleans up the documents library tree by deleting old YouTube source docs and their attached ai_responses (a normal housekeeping behaviour to keep the tree manageable, and not previously known to have any side-effect beyond the tree). Those soft-deleted ai_responses also became invisible to the digest's source-collection step — the digest could only ever surface ai_responses still visible in the library tree, which for active users meant only the most recent hour or so worth of content.

By 26 April 2026 the database held 181 ai_responses, of which 174 were soft-deleted, leaving the digest with effectively nothing to draw on.

**The architectural mistake:** coupling a system-internal function (digest source collection) to a UI-driven flag (library-tree visibility). The two are unrelated concerns. Library tree visibility is "what does the user want to look at right now?" Digest source availability is "what historical analyses exist in the database?" The user should be able to tidy the tree without breaking the digest.

**Fix:** One-line change in `subscription_manager.get_recent_responses`:

```python
# Before:
all_docs = db.db_get_all_documents()
# After:
all_docs = db.db_get_all_documents(include_deleted=True)
```

The `include_deleted=True` flag was already supported by `db_manager.db_get_all_documents`; the digest just wasn't passing it. The change also benefits the source-doc lookup later in `get_recent_responses`: when a YouTube source doc has been removed from the tree, the digest can still resolve its URL/title/published-date for the Sources section.

**Why no un-delete script was applied:** The user deleted those docs deliberately to keep the library tree manageable. Restoring them would re-clutter the tree and undo their housekeeping. The decoupling fix achieves the goal — digest works, tree stays tidy — without touching the soft-deleted state.

**Activation requirement:** Python caches module imports. After this fix is on disk, DocAnalyser must be **fully quit and restarted** for the running process to pick up the new `get_recent_responses` code. Until restart, digests still run with the old (broken) code.

**Generalisation — applies to any future system-internal query:** The same coupling mistake is latent in any other code path that uses `db_get_all_documents()` without `include_deleted=True`. When the **Research Agent / Corpus Query Mode** (Enhancement #23) is built, it should use `include_deleted=True` for the same reason — the corpus is the database, not the visible tree. Any future content-processing pipeline that queries the document library directly has the same concern. UI-facing functions (library tree rendering, search, branch picker) should keep the default `include_deleted=False`. The general rule:

> *If the function answers "what does the user want to see?" — filter by `is_deleted=0`.*
> *If the function answers "what is in the system?" — pass `include_deleted=True`.*

**Verification plan:** After DocAnalyser restart, open Subscriptions → Generate Digest. Should now produce ~10 sources (every subscription that has any ai_response on file, regardless of when), with a "no recent response found for…" warning naming the 8–9 subscriptions that have never been successfully checked (correct behaviour for The Contrarian, Larry Johnson, Pascal Lottaz, The Cradle, Peak Prosperity, Unherd, The West Report, Tucker Carlson, Brian Berletic).

**Diagnostic artefacts retained:** `diagnose_digest.py`, `diagnose_digest_2.py`, `diagnose_digest_3.py` in the project root, with their output files. Useful as DB-introspection examples should similar coupling bugs be suspected in future. Can be deleted once verification passes.

### P9 — Pipedream pipeline defunct, references to be removed

**Status:** Pipeline no longer operating. Codebase / docs cleanup pending.

**Background:** In April 2026 a Pipedream-based content-intelligence pipeline was built and tested. It monitored Substack authors (starting with Glenn Diesen) via RSS, processed each new article through the Anthropic API using the user's standard summarisation prompt, and uploaded the resulting summaries to a Google Drive folder named "Pipedream" for later import into DocAnalyser. There was an intent to extend coverage to YouTube channels (Alexander Mercouris was the first candidate). The pipeline is no longer in operation.

**Cleanup tasks:**
- Grep the codebase and the `Documentation/` and `Roadmap/` trees for any Pipedream-specific references (the literal word "Pipedream", any Drive folder logic that targets `/Pipedream` specifically, any code or doc framing the pipeline as current/upcoming) and remove or generalise them.
- The general architecture — *external pipeline → Drive folder → DocAnalyser import* — remains a valid pattern. Only the specific Pipedream implementation is being retired; the import-from-Drive path on the DocAnalyser side should be preserved.
- If a successor pipeline is later built (locally-scheduled in DocAnalyser itself, or a different SaaS), this cleanup gives a clean starting point rather than a mix of stale references to a discontinued tool.

**Context:** With the digest now working correctly after P8, and content arriving via Substack and YouTube subscriptions handled in-app, the rationale for an external pipeline has weakened. If background scheduling lands as part of Enhancement 5, the Pipedream-style use case can be served entirely from inside DocAnalyser.

**Effort:** Small — primarily a grep-and-prune pass. Worth doing before the next round of documentation work so new readers (and Claude in future sessions) don't encounter and act on stale references.

---

*Captured into Project Map: 25 April 2026*
*Updated with polish items P1–P5: 25 April 2026*
*Added P6 (migration preservation) and subscriptions snapshot: 26 April 2026*
*Added P7 (docx export bug + Google Doc delivery): 26 April 2026*
*Added P8 (digest / soft-delete decoupling — FIXED): 26 April 2026*
*Added P9 (Pipedream pipeline defunct — cleanup pending): 26 April 2026*
*Source: `Roadmap/DocAnalyser_Roadmap_Review_Updated_21_April_2026.docx`*
