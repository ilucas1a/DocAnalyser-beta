# DocAnalyser Development Roadmap — Review & Status Update

**Review Date:** February 2026
**Roadmap Version Reviewed:** 2.0 (January 2026)
**Current App Version:** 1.2.0 (beta)

---

## Executive Summary

The v2.0 roadmap planned 11 enhancements across 5 phases. Since the roadmap was written, substantial development has taken place. Of the 11 original enhancements, **5 are fully implemented**, **1 is partially implemented**, and **5 remain outstanding**. A 12th enhancement (Provider & Model Maintenance) has been identified and added during this review. Additionally, several significant features have been built that were not anticipated in the roadmap. The original phasing is now largely obsolete — Phases 1–3 are effectively complete — and the remaining items need re-prioritisation against the current state of the app and the competitive landscape.

---

## Enhancement Status: What's Done

### ✅ Enhancement 1: Prompt Import/Export — NOT YET DONE

Despite the Prompts Library having been rebuilt with a full tree structure (v3.0), the specific import/export functionality described in the roadmap — exporting selected prompts to JSON, importing with preview, duplicate handling — has **not** been implemented. The prompt_tree_manager.py has no import or export methods.

**However**, a curated default_prompts.json now ships with the installer and is automatically deployed on fresh installs (or auto-upgraded from stale minimal defaults — just implemented today). This partially addresses the "sharing" use case, but user-initiated import/export between installations is still missing.

**Status: Outstanding.** Still valuable as a relatively quick win.

---

### ✅ Enhancement 2: Web Response Import — DONE

Fully implemented. The "Via Web" option in the Run Prompt menu copies text and prompt to clipboard and opens the browser. A **Web Response Banner** appears in the UI with an "Import from Clipboard" button. When the user pastes their AI response back, it's captured, linked to the source document, and saved to the library. The full infrastructure is in place: `pending_web_response` context tracking, `show_web_response_banner()`, `capture_web_response()`, and `hide_web_response_banner()`.

**Status: Complete.**

---

### ✅ Enhancement 3: Tree Structure for Libraries — DONE

Both libraries have been rebuilt with hierarchical tree structures:

- **Prompts Library:** prompt_tree_manager.py v3.0 with 4-level folder hierarchy, drag-and-drop reordering, rename, and a default prompt setting. Ships with a curated starter set via default_prompts.json.
- **Documents Library:** document_tree_manager.py with tree-based folder organisation, source vs. response document distinction.

Both use a shared base (tree_manager_base.py).

**Status: Complete.** Exceeds the roadmap spec (which recommended capping at 3 levels; the implementation supports 4).

---

### ✅ Enhancement 4: Multi-Document Collection Analysis — DONE

Fully implemented. Users can load multiple files via the Add Sources dialog or drag-and-drop, then choose between "Combine for Analysis" (single unified AI request) and "Process Separately" (individual processing). The document list is reorderable with up/down buttons. The attachment_handler.py manages the multi-document queue.

The roadmap mentioned per-item "Send as image" vs "OCR to text" toggles and auto-filtering to vision-capable models — these specific sub-features may not be fully wired up, but the core multi-document workflow is solid.

**Status: Complete** (core workflow). Minor sub-features from the spec may be incomplete.

---

### ✅ Enhancement 5: Content Subscriptions & Auto-Processing — NOT DONE

No subscription monitoring, scheduled checking, or auto-processing pipeline has been implemented. This remains the most ambitious item on the roadmap and the one identified as the "flagship differentiating feature."

**Status: Outstanding.** Still high-value but high-effort.

---

### ✅ Enhancement 6: AssemblyAI Integration + Speaker Diarization — DONE

AssemblyAI is fully integrated as a third transcription engine alongside OpenAI Whisper (cloud) and Faster Whisper (local). Speaker diarization is supported with a configurable toggle in settings. The config.py defines AssemblyAI with `"supports_diarization": True`, and the UI includes a `diarization_var` checkbox.

**Status: Complete.**

---

### ✅ Enhancement 7: Multi-Model Peer Review — NOT DONE

No cross-model review, adjudication, or deliberation system has been implemented. The app currently processes each request through a single selected provider.

**Status: Outstanding.** Still an interesting differentiator but complex to build and niche in appeal.

---

### ✅ Enhancement 8: Zotero Integration — NOT DONE

No Zotero connection, bibliography browsing, or citation support exists. No Zotero-related code is present in the codebase.

**Status: Outstanding.** Value depends on target audience — high for academic users, negligible for general users.

---

### ✅ Enhancement 9: Research Mode / Corpus Analysis (RAG) — PARTIALLY DONE

A semantic_search.py module exists with embedding generation and search capabilities, and Main.py contains a `test_semantic_search()` function. However, the full RAG pipeline described in the roadmap — vector database (ChromaDB/FAISS), document chunking with overlap, background indexing, Research Mode UI toggle, corpus selection, retrieval with source attribution — is **not** implemented. What exists is more of a proof-of-concept than a usable feature.

The roadmap's own honest assessment still holds: for most users, uploading documents to Claude Projects or ChatGPT would be simpler and likely produce better synthesis. The genuine differentiator remains the local-first privacy angle.

**Status: Partially implemented** (foundations only). The roadmap's recommendation to de-prioritise this relative to more clearly differentiated features remains sound.

---

### ✅ Enhancement 10: Unified Viewer Multi-Source Display — DONE

Fully implemented. The Thread Viewer (thread_viewer.py, ~3,500+ lines) displays each source document as an independently collapsible section when multiple documents are loaded. Source sections have expand/collapse toggles, documents are tracked via `source_documents_for_viewer`, and the performance safeguards mentioned in the roadmap (default collapse when count > 3, lazy loading) have been addressed.

**Status: Complete.**

---

### ✅ Enhancement 11: Podcast RSS Support — NOT DONE

No podcast_handler.py, podcast_browser_dialog.py, or RSS parsing functionality exists. No `feedparser` dependency is installed. Podcast audio can be transcribed if the user manually provides the MP3 URL (via existing audio handling), but the automated RSS browsing, Apple/Spotify URL resolution, favourites, and batch episode selection described in the roadmap are not built.

**Status: Outstanding.** Has good synergy with Content Subscriptions (Enhancement 5) as noted in the roadmap.

---

### Enhancement 12: Provider & Model Maintenance (NEW — February 2026)

**Problem:** As AI providers release new models (and occasionally new providers emerge), DocAnalyser's hardcoded provider and model lists require manual code updates and a rebuild. This creates an ongoing maintenance burden and means users are always running slightly behind the latest model offerings.

**Two distinct sub-problems with different solutions:**

**12a: Keeping Model Lists Current**

The preferred approach is a **GitHub-hosted models.json** file that the app pulls via the existing update checker infrastructure. The developer curates the list (adding new models, removing deprecated ones — typically a 5-minute task when a new model is announced), and every user receives the update automatically on next check. This is simpler and more reliable than querying provider APIs directly, which return unfiltered lists full of embedding models, deprecated variants, and internal test models that would confuse users. The `model_updater.py` module already scaffolds this approach — it needs to be connected to a live remote file.

**12b: Making the Provider List Extensible**

Rather than a full plugin system (which would require users to write Python code), the recommended approach is adding a single **"OpenAI-Compatible" generic provider** option. Many newer AI providers — Groq, Together, Perplexity, Mistral, and local tools like LM Studio — use OpenAI-compatible API endpoints. A generic provider entry where the user configures a base URL, API key, and model name would cover all of these using the existing OpenAI client library pointed at a custom endpoint.

This would not replace the existing hardcoded providers (OpenAI, Anthropic, Google, xAI, DeepSeek, Ollama), which have bespoke integrations and should remain as built-in options. It would supplement them with an open-ended "bring your own provider" capability for power users.

**What this approach does NOT cover:** Providers with non-OpenAI-compatible APIs (notably Anthropic and Google) cannot be added this way. However, these are mature, stable integrations that change rarely and are better maintained as hardcoded providers — the effort to update them when needed is minimal (a few lines of code, perhaps 2–3 times per year).

**Decision:** Proceed with both 12a and 12b, but **not as an immediate priority**. Slot into Phase B alongside other differentiating features. Model list hosting (12a) is low-effort and could be done at any time. The generic OpenAI-compatible provider (12b) is a moderate effort with good extensibility payoff.

**Status: Planned.** Not yet implemented.

---

## Features Built That Aren't in the Roadmap

Several significant features have been developed since the roadmap was written (or were underway but not captured in it):

| Feature | Description |
|---------|-------------|
| **Ollama Local AI** | Full local AI support via Ollama (replaced LM Studio referenced in the roadmap). Includes local_ai_manager.py, local_ai_setup_dialog.py, local_model_manager.py for model download and management. |
| **Dictation / Speech-to-Text** | Voice input via dictation_dialog.py. Supports local-first (Faster Whisper), cloud (selected engine), and local-only modes. |
| **Standalone Conversations** | AI chat without loading any documents. Auto-generated titles, save-to-library option. |
| **First-Run Wizard** | Guided setup for new users (first_run_wizard.py, setup_wizard.py). |
| **Context Help System** | Right-click tooltips throughout the UI, loaded from help_texts.json (context_help.py). |
| **GitHub Update Checker** | Version checking against the GitHub repo (update_checker.py). |
| **Cost Tracking** | Logs AI API costs to cost_log.txt (cost_tracker.py). |
| **Smart OCR Caching** | Re-scan dialog (re-scan / use cached / cancel) for scanned PDFs, preventing stale Tesseract results. |
| **Substack Support** | Article and podcast extraction from Substack URLs (substack_utils.py). |
| **Spreadsheet Support** | CSV and XLSX file reading (openpyxl, pandas integration). |
| **Video Platform Support** | Multi-platform video handling beyond YouTube (video_platform_utils.py). |
| **Bundled Installer Tools** | Tesseract, Poppler, and FFmpeg bundled in the InnoSetup installer so users don't need to install them separately. |
| **Branch/Conversation Management** | Multiple conversation branches per source document with branch picker dialog. |
| **Auto-Save Responses** | Configurable automatic saving of AI responses (auto_save_responses.py, universal_document_saver.py). |
| **Curated Default Prompts** | Starter prompt library shipped via default_prompts.json with auto-upgrade from stale defaults (implemented today). |

---

## Revised Phasing Recommendation

Given the current state, the original 5-phase structure is obsolete. Here is a suggested re-phasing of the **remaining** work:

### Phase A: Quick Wins (Days)

1. **Prompt Import/Export** (Enhancement 1) — The tree structure is already built; adding export-to-JSON and import-with-preview is a natural extension. Low effort, immediate user value for anyone wanting to share prompts between machines or with other users.

2. **GitHub-Hosted Model Lists** (Enhancement 12a) — Publish a curated models.json to the GitHub repo and wire up model_updater.py to pull it. Minimal code change, eliminates the need for a full rebuild every time a new model is released.

### Phase B: Differentiating Features (Weeks)

3. **Podcast RSS Support** (Enhancement 11) — Estimated at 2.5–3 days in the roadmap. Provides a streamlined workflow that no web AI interface offers, and builds ~60% of the infrastructure needed for Content Subscriptions.

4. **Content Subscriptions & Auto-Processing** (Enhancement 5) — The flagship differentiator. With Podcast RSS providing the RSS infrastructure and the existing YouTube/Substack handlers, the remaining work is the scheduling system, auto-processing pipeline, and "What's New" dashboard. This is the feature most likely to make the "why not just use ChatGPT?" question irrelevant.

5. **OpenAI-Compatible Generic Provider** (Enhancement 12b) — Add a single configurable provider slot that works with any OpenAI-compatible API endpoint (Groq, Together, Perplexity, Mistral, LM Studio, etc.). Moderate effort with good extensibility payoff. Not urgent but worth doing before wider release.

### Phase C: Power User Features (Weeks–Months)

4. **Multi-Model Peer Review** (Enhancement 7) — Interesting but niche. Worth building after the differentiating features are in place, as it leverages DocAnalyser's unique multi-provider architecture.

5. **Zotero Integration** (Enhancement 8) — Only if targeting academic users. Consider whether the user base justifies the effort.

6. **Research Mode / RAG** (Enhancement 9) — Continue to de-prioritise as the roadmap recommends. The local-privacy angle is the only genuine differentiator here, and the effort is substantial.

---

## Roadmap Corrections Needed

A few factual items in the v2.0 roadmap are now outdated:

| Item | Roadmap Says | Current Reality |
|------|-------------|----------------|
| Local AI provider | "LM Studio" | Now **Ollama** with full setup wizard |
| AI Providers count | 5 (OpenAI, Anthropic, Google, xAI, DeepSeek) | **6 cloud + 1 local** (adds Ollama) |
| Content Sources | Doesn't mention CSV, XLSX, Substack | All now supported |
| Dictation | Not mentioned | Fully implemented |
| Standalone Conversations | Not mentioned | Fully implemented |
| Installer bundling | Not mentioned | Tesseract, Poppler, FFmpeg all bundled |
| Tree structure depth | "Cap at 3 levels" | Implemented at **4 levels** |
| Enhancement 10 description | "Proposed Behaviour" | **Already built and working** |

---

## Strategic Observation

The roadmap's Clarity AI section remains relevant as a long-term direction, but DocAnalyser has grown substantially beyond what was anticipated. The question worth revisiting is whether the Tkinter architecture is becoming a bottleneck for the features that remain (particularly Content Subscriptions, which needs background scheduling and a dashboard UI that Tkinter handles awkwardly), or whether it's still adequate for the remaining roadmap items before a potential Clarity AI rewrite.

For the immediate term, the highest-impact development path is: **Prompt Import/Export → GitHub Model Lists → Podcast RSS → Content Subscriptions → Generic Provider**. The first two are quick wins that reduce ongoing maintenance burden and improve user experience immediately. The next two are the differentiating features that give DocAnalyser a compelling answer to "why not just use the web interface?" The generic provider rounds out the extensibility story before wider release.
