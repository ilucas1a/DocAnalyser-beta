# Claude Skills Integration — Exploration Notes

**Status:** Parked for later exploration.
**Captured:** 4 May 2026.
**Trigger:** Side question raised during the audio-editing upgrade work, asking whether existing Claude skills could fruitfully be integrated into DocAnalyser, and whether there's scope for new skills.
**Priority:** Not urgent. Worth a proper look once the in-progress audio-transcription editing upgrade and Enhancement 5 (Subscriptions completion) are off the runway. Strongest practical convergence is with Enhancement 23 (Research Agent) — see "Timing" below.

---

## What "Claude skills" actually are

Folders shipped with a `SKILL.md` file (plus optional helper scripts and example fixtures) that tell Claude how to do a specific kind of task well. They're a feature of Claude's chat / Claude Code / Agent SDK environments — *not* something exposed by the bare `messages.create` API that `ai_handler.py` currently uses. Consequence: "integrating skills into DocAnalyser" splits into three different things with very different effort/payoff profiles. They should be considered separately.

---

## Three categories of opportunity

### Category 1 — Existing Anthropic skills, used as reference material

Skills currently shipped by Anthropic that touch areas DocAnalyser already operates in:

- **pdf-reading** — PDF text extraction, OCR fallback strategies, page rasterisation, table extraction, format-by-document-type heuristics. Direct overlap with `ocr_handler.py`. Worth a one-time read-through against the existing code looking for edge cases (scanned-with-text-overlay hybrids, slide-deck PDFs, forms with fillable fields) where DocAnalyser may be suboptimal.
- **pdf** (creation/manipulation) — relevant to `document_export.py` and `doc_formatter.py`. No immediate need; bookmark for any future PDF feature work (form filling, watermarking, merging).
- **docx** — directly relevant to the recent P7 work on hyperlinks and bookmarks via `docx_helpers.py`. Worth comparing the skill's recommendations against what was implemented — particularly for numbered lists, anchored headings, and tracked changes if those ever come up.
- **xlsx** — minor relevance now (DocAnalyser only reads spreadsheets via `smart_load`). Becomes relevant if a "digest as structured table" or "subscription dashboard export" is ever built.
- **frontend-design** — not relevant to current DocAnalyser. Bookmark for if/when Clarity AI work begins.
- **skill-creator** — meta-skill. The right tool for building anything in Category 2 or 3.

**Honest assessment of this category:** modest, mostly-confirmatory value. DocAnalyser already does most of what these skills recommend. The win is one targeted re-read pass per skill, looking for "hadn't thought of that" moments, and pulling those into existing modules. Not a project — a couple of half-day sessions, slotted in alongside other work when convenient.

---

### Category 2 — Adopt the skill *pattern* inside DocAnalyser (the strongest play)

DocAnalyser currently stores AI guidance as flat prompt text (`prompts.json`) plus a handful of class constants like `_AUDIO_LINK_PROMPT` in `Main.py`. The skill-folder pattern (prompt + guidelines + examples + optional validator script) is a better fit for several jobs that have outgrown plain prompts.

**Concrete candidates, ranked by how strongly each benefits from the upgrade:**

1. **Research Agent / Corpus Query Mode (Enhancement 23) — strongest case.** Not yet built. Hard to get right without explicit guidance about citation format, when to refuse, conflicting-source handling, on-topic boundaries. Building it as a skill from day one — instead of a 200-line prompt buried in a function — pays dividends immediately and keeps it editable as the corpus grows. **Recommendation: scaffold Enhancement 23 as a skill from the start.**
2. **Audio-linked summary** — currently `_AUDIO_LINK_PROMPT` constant in `Main.py`, with the known limitation that local models don't reliably follow the `[SOURCE: "..."]` format. A skill folder would co-locate prompt + format spec + 2–3 worked examples + a validator (does the output actually contain `[SOURCE:` markers?). The validator turns the "needs cloud model" warning from a heuristic into an empirical post-check.
3. **Subscription digest / tiered briefing** — `subscription_manager.generate_digest()`. Has had real-world iteration (P1–P5 polish items, P8 soft-delete coupling bug). A skill folder gives a place for the prompt, chunking strategy, source-collection rules, and representative inputs+outputs as test fixtures.
4. **Interviewee extraction** — `subscription_manager._extract_interviewee`. April 2026 widening from 800 → 5000 chars and host-as-context addition is the kind of evolution that wants worked examples in a skill folder, not comments in a function.
5. **Voice-edit command parser** — `voice_edit_dialog.py`. Less obvious. A grammar spec + examples + validator would make adding new commands much cleaner.

**Architecture sketch (for when this is picked up):**

- New `skills/` subdirectory under DocAnalyser. Each subfolder = one skill: `SKILL.md` (system prompt + guidelines), optional `examples/` (input/output pairs), optional `validator.py` (deterministic post-check).
- `ai_handler.py` gains `call_with_skill(skill_name, inputs, ...)` — loads `SKILL.md` as system prompt, runs the AI call, runs the validator if present.
- Migrate one prompt as a proof of concept (audio-linked summary is the obvious first candidate — it's small, has a known failure mode, and the validator is straightforward).
- Then migrate digest and interviewee extraction.
- Build Enhancement 23 (Research Agent) natively as a skill from the start.

**Effort:** medium. ~1–2 weeks to bootstrap the architecture and migrate one or two existing prompts. Scales well as more AI tasks accumulate.

**Strategic fit:** dovetails with Enhancement 15 (User-Facing Message Editor) and Enhancement 16 (Settings Registry). All three are part of the same "extract hardcoded knowledge into editable, versioned files" theme. If those Phase A items happen anyway, doing them in a way that anticipates the skill pattern is cheap insurance.

---

### Category 3 — A user skill for working *on* DocAnalyser with Claude

Separate from anything in the app itself: a personal skill that loads whenever Claude works on DocAnalyser, in any session and any future Claude model.

**Proposed: `docanalyser-conventions` skill.** Contents:

- The 10-mixin inheritance pattern in `Main.py`
- Preference for surgical edits over rewrites
- The `apply_*.py` patch script convention with idempotency markers (`[SKIP]` if already applied)
- Git-commit-before-major-changes rule
- The two-key metadata convention (`source_document_id` *or* `parent_document_id`)
- The PROVIDER_REGISTRY single-source-of-truth rule
- Pointer to the project map at `Documentation/ProjectMap/00_INDEX.md` as the entry point for any new session
- Coding style preferences (verification-driven, design-before-implement)

**Effort:** small. A single SKILL.md, maybe 200 lines. Use the `skill-creator` skill to build it.

**Payoff:** every future Claude session adopts the patterns from turn one, instead of needing the project-map walk-through (~30k tokens) every time. Recurring time saving on every DocAnalyser session.

**Limitation:** depends on how/where the skill is loaded. Works automatically in Claude Code and in chat sessions where the skill has been registered; not automatic in the bare API. Worth checking current Anthropic documentation on user skill loading at the time this is picked up — the mechanics may have evolved.

---

## Recommendation summary (the "if you only do one thing" version)

1. **First (lowest effort, highest recurring payoff):** build the `docanalyser-conventions` user skill. A couple of hours.
2. **When Enhancement 23 starts:** scaffold the Research Agent as a skill from day one. Same effort as building a hardcoded prompt; far better long-term shape.
3. **Optional refactor, do later if at all:** migrate the existing AI prompts (audio-linked summary, digest, interviewee extraction) into the skill pattern. Worth doing only once the duplication starts being painful — likely after the third or fourth task lands.

Category 1 (cherry-picking from existing Anthropic skills) is a slot-in-when-convenient activity, not a project.

---

## Timing / prerequisites

**Don't pick up before:**
- The in-progress audio-transcription editing upgrade is finished (Audio_Editing_* documents in this folder).
- Enhancement 5 (Subscriptions completion — scheduling + "What's New" dashboard + shakedown) has had its main pass.

**Natural trigger to pick up:**
- When Enhancement 23 (Research Agent / Corpus Query Mode) is the next thing on the list. That's the moment when Category 2 stops being a "nice refactor" and starts being a "the right way to build this".

**Quick wins available before that trigger:**
- The `docanalyser-conventions` user skill (Category 3) — can be done at any time, in a single sitting.
- Cherry-picked re-reads of `pdf-reading` and `docx` skills against the corresponding DocAnalyser modules.

---

## Open questions to resolve when this is picked up

1. What is the current state of skill-loading in the Anthropic API / chat / Claude Code environments? The mechanics may have evolved since this note was written. Check current docs.
2. Is there value in the Anthropic-shipped skills being *literally* embedded in DocAnalyser (e.g., copied into a `vendor/skills/` directory and loaded by `ai_handler.py`), or is the value purely as reference material? Probably the latter, but worth a five-minute think when this is picked up.
3. If the skill pattern is adopted internally (Category 2), does it replace `prompts.json` entirely, or coexist? Default assumption: coexist — `prompts.json` remains for user-edited free-text prompts, skills are for system-defined structured tasks.
4. Where does the `docanalyser-conventions` user skill (Category 3) live and how is it invoked? Is it stored in the repo (so it's portable across machines / Claude environments) or is it a personal-environment artefact? Default: store the SKILL.md in the repo at `Documentation/ClaudeContext/` or similar, so any environment that supports skill loading can pick it up.

---

*Source: chat conversation, 4 May 2026, after a full project-map walk-through. The reasoning chain is preserved here so the next read can pick it up cold.*
