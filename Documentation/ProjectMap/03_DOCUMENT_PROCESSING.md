# Project Map: Document Processing (OCR, Audio, Vision)

## ocr_handler.py (1,819 lines)
- **Purpose:** Core OCR processing engine — image and scanned PDF text extraction with corruption protection
- **Dependencies:** os, sys, json, hashlib, pathlib, PIL, pytesseract, pdf2image, requests
- **Called By:** ocr_processing.py (mixin), ocr_dialog.py, Main.py
- **Known Limitation:** PDFs with "Object X Y ref" corruption can cause infinite loops at C library level

### Cache Management:
- `ensure_ocr_cache()` — creates cache directory
- `get_ocr_cache_path(filepath, quality, language)` → str
- `load_cached_ocr(filepath, quality, language)` → list or None
- `save_ocr_cache(filepath, quality, language, entries)`
- `get_cache_info()` → dict — stats on cache usage
- `clear_cache(cache_type)` → tuple — clears OCR or audio cache

### Tesseract/Poppler Configuration:
- `get_tessdata_dir()` → str or None
- `find_tesseract_windows()` → str or None — auto-detect Tesseract install
- `configure_tesseract_path(custom_path)` — sets pytesseract path
- `check_ocr_availability()` → tuple — tests Tesseract presence
- `get_tesseract_install_info()` → tuple
- `find_poppler_path()` → str or None — auto-detect Poppler install
- `check_poppler_availability()` → tuple
- `get_poppler_install_info()` → tuple

### PDF Processing:
- `test_pdf_with_subprocess(filepath, timeout)` → tuple — safe pre-check for corrupt PDFs
- `pre_screen_pdf_for_ocr(filepath, log_func)` → bool — should PDF use OCR?
- `offer_pdf_repair(filepath, log_func)` — suggests repair tools for corrupt PDFs
- `try_cloud_ai_pdf_fallback(filepath, provider, model, api_key, ...)` — cloud fallback for failed local OCR
- `extract_text_from_pdf_smart(filepath, ...)` — main PDF text extraction with smart routing
- `extract_text_from_pdf_with_ocr(filepath, language, ...)` — full OCR pipeline for scanned PDFs
- `is_pdf_scanned(filepath)` → bool — detects if PDF needs OCR

### Image OCR:
- `fix_ocr_encoding_artifacts(text)` → str — cleans mojibake/encoding issues
- `get_tesseract_confidence(image, language, config)` → tuple — quality score
- `preprocess_image_for_ocr(image, quality_preset)` → Image — enhance for better OCR
- `extract_text_from_image_with_options(image_path, ...)` → dict
- `ocr_with_cloud_ai(image_path, provider, model, api_key, ...)` — cloud vision fallback
- `ocr_image_smart(image_path, ...)` — smart routing: local → confidence check → cloud offer
- `process_multiple_images_ocr(image_paths, ...)` — batch OCR for multi-page documents
- `process_single_image_ocr(image_path, ...)` — single image OCR
- `check_cloud_vision_configured(config)` → tuple

---

## ocr_dialog.py (1,516 lines)
- **Purpose:** Multi-Image OCR Dialog — modal Tkinter dialog for processing multiple images/pages as one document
- **Pattern:** Purely UI — all OCR logic delegates to ocr_handler.py
- **Dependencies:** tkinter, PIL, pdf2image
- **Called By:** Main.py, vision_processing.py

### Class: MultiImageOCRDialog
- File management: add, remove, reorder, paste, drag-and-drop images
- PDF → image conversion for page-by-page OCR
- Text type selection (printed vs handwriting)
- OCR mode selection (local_first, cloud_direct, cloud_pdf)
- Progress display during processing
- Result preview with copy/save/voice-edit options
- Cloud AI retry offer when local OCR confidence is low
- Export to TXT, MD, DOCX formats

---

## ocr_processing.py (1,377 lines)
- **Purpose:** OCR processing orchestration and web content fetching — **Mixin class** extracted from Main.py
- **Pattern:** `OCRProcessingMixin` — mixed into the main app class, uses `self.xxx` references
- **Dependencies:** ocr_handler, document_fetcher, ai_handler
- **Called By:** Main.py (mixed in via inheritance)

### Key Methods (all on self/app instance):
- `_handle_ocr_fetch(success, result, title)` — result handler
- `process_ocr()` — initiates OCR workflow
- `_ask_text_type(image_path)` — dialog: printed vs handwriting vs cloud PDF
- `_ask_text_type_pdf(pdf_path)` — PDF-specific OCR mode selection dialog
- `_ask_cloud_ai_escalation(confidence, provider, model)` — offer cloud retry
- `_ask_text_type_for_image()` — image-specific type dialog
- `_process_image_with_cloud_ai(image_path, title)` — cloud vision processing
- `_process_pdf_with_cloud_ai(pdf_path, title, text_type)` — cloud PDF processing
- `_process_ocr_thread()` — threaded OCR execution
- `_handle_ocr_result(success, result, title)` — result display
- `fetch_web()` — web URL content fetching
- `_fetch_web_thread()` — threaded web fetch
- `process_web_video()` — web video processing (non-YouTube)
- `process_web_pdf_with_ocr()` — download and OCR a web-hosted PDF
- `_handle_web_result(success, result, title, doc_type, web_metadata)` — web result handler

---

## audio_handler.py (1,020 lines)
- **Purpose:** Audio/video transcription engine with progressive display and caching
- **Key Feature:** Shows transcribed text in real-time as segments are processed
- **Dependencies:** os, json, hashlib, pathlib, pydub, openai, faster_whisper, assemblyai
- **Called By:** Main.py (for audio file processing)

### Cache Functions:
- `get_custom_cache_dir()` → Path — custom whisper model cache location
- `set_whisper_cache_dir()` — configures HuggingFace cache
- `get_cache_dir()` → str
- `get_cache_key(audio_path, engine, model, language, use_vad)` → str
- `get_cached_transcription(cache_key)` → dict or None
- `save_to_cache(cache_key, result)`
- `clear_audio_cache()`

### Transcription Functions:
- `format_timestamp(seconds)` → str
- `transcribe_with_whisper(audio_path, api_key, language, ...)` — OpenAI Whisper API
- `transcribe_with_faster_whisper(audio_path, model, language, ...)` — local faster-whisper
- `transcribe_audio(audio_path, engine, api_key, ...)` — dispatcher for engine selection
- `transcribe_audio_file(audio_path, engine, config, ...)` — main entry point, handles chunking of long audio
- `transcribe_youtube_audio(video_url, config, ...)` — YouTube audio extraction + transcription

---

## transcription_handler.py (788 lines)
- **Purpose:** Microphone recording and speech-to-text for dictation feature
- **Dependencies:** sounddevice, scipy, faster_whisper, openai, assemblyai
- **Called By:** dictation_dialog.py

### Model Management:
- `get_models_directory()` → Path
- `is_model_downloaded(model_name)` → bool
- `get_downloaded_models()` → list
- `download_model(model_name, progress_callback)` → (bool, str)

### Class: AudioRecorder
- `start_recording()` → (bool, str) — starts microphone capture
- `stop_recording()` → (bool, str, filepath) — stops and saves WAV
- `is_recording()` → bool
- `get_duration()` → float

### Transcription Functions:
- `check_microphone_available()` → (bool, str)
- `get_input_devices()` → list
- `transcribe_local(audio_path, model_name, language, ...)` — faster-whisper local
- `transcribe_cloud(audio_path, api_key, language)` — OpenAI Whisper cloud
- `transcribe_assemblyai(audio_path, api_key, language, ...)` — AssemblyAI with optional diarization
- `transcribe_audio(audio_path, config, ...)` — dispatcher with local→cloud fallback chain
- `check_transcription_availability()` → dict
- `get_transcription_install_info()` → str

---

## vision_processing.py (968 lines)
- **Purpose:** Vision/image processing and document utility methods — **Mixin class** extracted from Main.py
- **Pattern:** `VisionProcessingMixin` — mixed into main app class
- **Dependencies:** ai_handler, ocr_dialog, document_library
- **Called By:** Main.py (mixed in via inheritance)

### Key Methods:
- `_show_multi_image_dialog(ocr_files)` / `_show_multi_ocr_dialog(ocr_files)` — launches MultiImageOCRDialog
- `_show_reorder_dialog(parent, files)` — drag-to-reorder files dialog
- `_process_images_with_vision(ocr_files, combine)` — batch vision API processing
- `_process_pdf_pages_direct_vision(pdf_path)` — send PDF pages to vision AI
- `_save_separate_vision_results(entries, ocr_files)` — save per-page results
- `_process_single_image_with_vision(image_path)` — single image vision
- `_provider_supports_vision(provider)` → bool
- `_vision_openai(api_key, model, image_data, mime_type, prompt)` — direct OpenAI vision call
- `_vision_anthropic(api_key, model, image_data, mime_type, prompt)` — direct Anthropic vision call
- `_vision_google(api_key, model, image_data, mime_type, prompt)` — direct Google vision call
- `refresh_library()` — refreshes document library display
- `convert_to_source_document()` — converts current text to source document
- `save_ai_output_as_product_document(output_text)` — saves AI output to library

---

## transcript_cleaner.py (~600 lines)
- **Purpose:** Core transcript processing engine — converts raw faster-whisper entries into cleaned, consolidated, speaker-labelled paragraphs ready for DocAnalyser's document model.
- **Design:** Intentionally self-contained — imports nothing from DocAnalyser so it can be tested independently. Includes a standalone CLI runner (`python transcript_cleaner.py dummy_transcript.txt`).
- **Dependencies:** re, sys, os, argparse (stdlib only)
- **Called By:** transcript_cleanup_dialog.py (via `clean_transcript()`), standalone test runner

### Tuning Constants (top of file):
| Constant | Default | Role |
|---|---|---|
| `FILLER_DURATION_THRESHOLD` | 0.60s | Segments shorter than this + text is noise → discarded |
| `SENTENCE_GAP_THRESHOLD` | 1.8s | Gap below this → same sentence still in progress |
| `PARAGRAPH_GAP_THRESHOLD` | 3.5s | Gap above this → new paragraph |
| `SHORT_WORD_THRESHOLD` | 8 words | Paragraph at/below this is "interviewer-like" |
| `LONG_RESPONSE_WORD_COUNT` | 50 words | Triggers speaker-switch detection |

### Processing Pipeline (6 phases):

**Phase 1 — Filler removal** (`strip_fillers(entries)` → (cleaned, count)):
- Discards segments whose text is a known filler word (`FILLER_WORDS`: uh, um, mm, etc.)
- Retains back-channel tokens (`BACKCHANNEL_WORDS`: mm-hmm, right, yeah, etc.) but converts them to bracketed annotations: `[Right]`

**Phase 2 — Sentence consolidation** (`consolidate_sentences(entries)` → sentences):
- Joins consecutive segments into sentences using gap threshold + terminal punctuation detection
- Back-channel annotations absorbed inline into surrounding sentence

**Phase 3 — Heuristic speaker classification** (`classify_speakers_heuristic(sentences)` → sentences):
- Assigns SPEAKER_A (interviewee) / SPEAKER_B (interviewer) using three signals: ends with `?`, very short paragraph, follows a long block from the other speaker
- Always marks output `provisional=True` — these are suggestions, not reliable determinations
- Runs **before** paragraph consolidation so speaker changes can drive paragraph boundaries

**Phase 4 — Paragraph consolidation** (`consolidate_paragraphs(sentences)` → paragraphs):
- Groups sentences into paragraphs; new paragraph on gap > threshold OR speaker change
- Preserves per-sentence timestamps in `entry["sentences"]` for fine-grained audio-seek

**Phase 5 — Pyannote alignment** (`apply_diarization(paragraphs, audio_path, hf_token, ...)` → (paragraphs, bool)):
- Optional, Tier 2. Replaces heuristic labels with acoustically-verified `SPEAKER_00`/`SPEAKER_01` from `diarization_handler.run_diarization()`.
- Degrades gracefully: returns original heuristic paragraphs unchanged if diarization unavailable or fails.
- **Currently never called** — `transcript_cleanup_dialog.py` has `PYANNOTE_ENABLED = False`.

**Phase 6 — Speaker name substitution** (`apply_speaker_names(paragraphs, name_map)` → paragraphs):
- Replaces internal IDs (e.g. `SPEAKER_A`) with real names from `name_map` dict.
- IDs not in `name_map` are left unchanged.

### Top-Level Entry Point:
- `clean_transcript(entries, audio_path, hf_token, name_map, use_diarization, keep_backchannels, progress_callback)` → dict
  - Returns: `{paragraphs, fillers_removed, diarization_used, speaker_ids, warnings}`

### Output Conversion:
- `paragraphs_to_entries(paragraphs)` → List[Dict] — converts to DocAnalyser's native entries format; preserves `sentences` sub-list for audio seek
- `paragraphs_to_text(paragraphs, include_timestamps, include_speaker_labels, provisional_note)` → str — plain text output

---

## diarization_handler.py (~400 lines)
- **Purpose:** Pyannote.audio wrapper providing Tier 2 speaker diarization for DocAnalyser.
- **Design:** Intentionally isolated — its absence (pyannote not installed, no HuggingFace token, model not downloaded) never causes an import error or crash anywhere else. All public functions return a success flag as their first value.
- **Status:** Code is complete and retained for future use. Currently **disabled** in the app via `PYANNOTE_ENABLED = False` in `transcript_cleanup_dialog.py`. Re-enable by setting that flag to `True`.
- **Dependencies:** pyannote.audio, torch, torchaudio, huggingface_hub (all optional — checked at runtime)
- **Called By:** transcript_cleaner.py (Phase 5), hf_setup_wizard.py (model download), transcript_cleanup_dialog.py (availability checks — short-circuited when disabled)

### Key Constant:
- `MODEL_ID = "pyannote/speaker-diarization-3.1"` — change here to switch to a newer community model

### Type Alias:
- `SpeakerTimeline = List[Tuple[float, float, str]]` — list of (start_secs, end_secs, speaker_id) sorted by start time

### Availability Checks:
- `is_pyannote_installed()` → bool
- `is_torch_available()` → bool
- `is_model_cached(hf_token)` → bool — lightweight check via `huggingface_hub.try_to_load_from_cache`
- `is_available(hf_token)` → bool — True only when all four conditions met (pyannote, torch, token, cached model)
- `get_status(hf_token)` → dict — `{ready, pyannote, torch, token_present, model_cached, message}` for UI display

### Model Download:
- `download_model(hf_token, progress_callback)` → (bool, str) — one-time ~1.5 GB download via `Pipeline.from_pretrained()`. Provides user-friendly error messages for 401/403/connection failures.

### Diarization:
- `run_diarization(audio_path, hf_token, num_speakers, min_speakers, max_speakers, progress_callback)` → (bool, SpeakerTimeline)
  - Loads pipeline, moves to GPU if available (falls back to CPU)
  - CPU performance: roughly 1× real-time (60-min recording ≈ 55–70 min processing)
  - Uses `ProgressHook` if available (newer pyannote); falls back gracefully for older versions
  - Normalises speaker labels to uppercase (`SPEAKER_00`, `SPEAKER_01`, etc.)

### Timeline Queries:
- `speaker_at(timeline, time_seconds)` → str or None — returns speaker at given time; falls back to nearest segment midpoint if no exact coverage
- `dominant_speaker(timeline, start_seconds, end_seconds)` → str or None — duration-weighted lookup for longer paragraphs spanning speaker transitions
- `get_speaker_ids(timeline)` → List[str] — sorted unique speaker IDs

### Performance Note:
On CPU-only hardware, processing time ≈ recording duration. This is the primary reason the feature is disabled for general release — most community users' computers lack the required GPU.
