# Roadmap Addition — Enhancement 24: Faster Whisper Large V3 Turbo

**Drafted:** 21 April 2026
**For inclusion in:** DocAnalyser_Roadmap_Review_Updated_17_April_2026.docx
**Target release:** Next beta

Two insertions to make. Paste each block into Word with Track Changes turned on.

---

## Insertion 1 — New item in the Phase A list

**Location:** In the "Revised Phasing Recommendation → Phase A: Quick Wins (Days)" section, add as a new item 10 immediately after item 9 ("Function-Level Documentation").

**Content to paste:**

**10. Faster Whisper Large V3 Turbo** (Enhancement 24) — Add large-v3-turbo as a new faster-whisper model option alongside Tiny through Large V3. Roughly the same disk footprint as Medium (~1.6 GB) but with close to Large V3 accuracy on English speech, and ~4× faster than Large V3. Should become the recommended local default. Implementation is narrow: a new entry in the faster-whisper model list plus label in the Audio & Transcription Settings dialog and the Dictation local-model dropdown. Target: next beta release.

*Formatting note: "10. Faster Whisper Large V3 Turbo" is bold, matching items 1–9. Everything after "(Enhancement 24) —" is plain text.*

---

## Insertion 2 — New Enhancement 24 section

**Location:** At the end of the document, immediately after the closing italic summary of Enhancement 23 ("Substantial new capability area (3–5 weeks)...").

**Content to paste:**

### Enhancement 24: Faster Whisper Large V3 Turbo (NEW)

**Status:** Planned — target next beta release

DocAnalyser currently offers five faster-whisper model sizes via the Audio & Transcription Settings dialog: Tiny, Base, Small, Medium, and Large V3. Real-world testing against a commercial cloud transcription service on a Vietnam-themed oral history interview highlighted that the Medium model — the current pragmatic default — loses too many proper nouns and domain terms on accented English, while Large V3 is meaningfully slower and has a larger disk and memory footprint than many users will tolerate. OpenAI's large-v3-turbo model (released mid-2024) sits between the two: it is a pruned and distilled variant of Large V3 with the decoder reduced from 32 layers to 4, giving roughly 4× faster inference at near-identical English accuracy.

On disk, large-v3-turbo is approximately 1.6 GB — essentially the same as Medium (1.5 GB) and about half the size of Large V3 (~3 GB). VRAM and RAM requirements are also roughly half those of Large V3, putting the model comfortably within reach of a typical laptop. For DocAnalyser's primary audience — oral historians and community researchers working with English-language interview audio — it should therefore become the new recommended local default, with Medium retained for low-spec machines and Large V3 retained as the maximum-quality option. The one genuine caveat is that turbo was trained on a narrower set of languages than Large V3; for non-English workflows Large V3 remains the stronger choice.

Implementation is narrow in scope. The faster-whisper model list is referenced in a small number of places: the Audio & Transcription Settings dialog (the Faster Whisper Model Size radio group), the Dictation local-model dropdown, and the underlying transcription paths in `audio_handler.transcribe_with_faster_whisper()` and `transcription_handler.transcribe_local()`. The model identifier `large-v3-turbo` is accepted directly by faster-whisper ≥ 1.0.3, so no library change is required provided the installed version meets that floor (worth a dependency-check on startup). Suggested label in the UI: "Large V3 Turbo — Recommended (~1.6 GB, fast)", with Medium repositioned as the budget option and Large V3 retained as the maximum-accuracy option. The first run after the update should download the model transparently using the same mechanism already in place for the other faster-whisper models.

Two secondary options worth considering at the same time, given they share the same settings surface: (a) an optional `initial_prompt` field in the Audio & Transcription Settings dialog that lets users seed Whisper's vocabulary with project-specific terms (place names, people, acronyms) — a cheap, high-leverage accuracy lift that benefits every model size, not just turbo; and (b) a post-transcription glossary substitution step that applies a user-supplied term map after transcription completes. Both pair naturally with the Workspaces concept (Enhancement 13), where the prompt and glossary could be workspace-scoped. Neither is a prerequisite for shipping turbo, but they are adjacent enough that doing them together would be efficient if capacity allows.

*Low effort (UI label plus a model-list entry and a faster-whisper version check). High value — meaningfully closes the accuracy gap with commercial cloud transcription services at no practical cost to users with modest hardware. Slot into Phase A for the next beta release.*

*Formatting notes:*
- *"Enhancement 24: Faster Whisper Large V3 Turbo (NEW)" is a Heading 2, matching Enhancements 21–23.*
- *"Status:" is bold, the rest of that line is plain.*
- *The final paragraph is italic in grey (#666666), matching the closing summaries of other enhancements.*
- *Everything else is plain body text.*

---

## How to paste into Word

1. Open `DocAnalyser_Roadmap_Review_Updated_17_April_2026.docx` in Word.
2. Turn on Track Changes (Review ribbon → Track Changes).
3. For Insertion 1: scroll to the end of Phase A, position the cursor at the end of item 9, press Enter, and paste the item 10 block. Apply bold to the "10. Faster Whisper Large V3 Turbo" portion.
4. For Insertion 2: scroll to the end of the document, position the cursor after the italic summary of Enhancement 23, press Enter, and paste the Enhancement 24 block. Apply the Heading 2 style to the title line, bold the "Status:" label, and italicise/grey the closing summary paragraph.
5. Save.
