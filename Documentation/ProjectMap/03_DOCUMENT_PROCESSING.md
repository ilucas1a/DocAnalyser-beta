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
