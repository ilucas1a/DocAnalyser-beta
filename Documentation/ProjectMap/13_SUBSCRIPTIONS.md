# 13 - Subscriptions

## Overview
Two modules implementing a content subscription system that monitors YouTube channels, Substack publications, and RSS feeds for new items, fetches their content, runs AI processing with a user-configured prompt, and saves both the source document and the AI output to the Documents Library.

> **Status (April 2026): In development — functional but known bugs remain. Manual "Check Now" operation works; scheduling hooks are present in the data model but not yet wired up.**

**Data file:** `%APPDATA%\DocAnalyser_Beta\subscriptions.json`

---

## subscription_manager.py (~550 lines)
**Purpose:** Pure logic engine — subscription data persistence, feed fetching, content retrieval, AI processing, and library saving. No UI code.

**Called By:** `subscription_dialog.py`

---

### Data Model

`default_subscription()` returns a dict with all fields at their defaults:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `id` | str | uuid hex | Unique identifier |
| `name` | str | `""` | Display name |
| `type` | str | `"youtube_channel"` | `youtube_channel` \| `substack` \| `rss` |
| `url` | str | `""` | Channel/feed URL |
| `channel_id` | str | `""` | Resolved YouTube channel ID (YouTube only) |
| `enabled` | bool | `True` | Whether to include in Check All |
| `prompt_name` | str | `""` | Display name of the prompt |
| `prompt_text` | str | `""` | Full prompt text sent to AI |
| `min_duration` | int | `25` | Minimum video length in minutes (YouTube only; 0 = no filter) |
| `look_back_hours` | int | `24` | Only process items published within last N hours (0 = all new) |
| `last_checked` | str \| None | `None` | ISO datetime of last check |
| `seen_guids` | list | `[]` | Video IDs / post GUIDs already processed — prevents reprocessing |
| `schedule_enabled` | bool | `False` | Reserved for future scheduling (not yet active) |
| `check_interval_hours` | int | `6` | Reserved for future scheduling |
| `check_time` | str | `"06:00"` | Reserved for future scheduling |

**Persistence:** `load_subscriptions()` / `save_subscriptions(subs)` — atomic write via `.tmp` rename.

**CRUD:** `add_subscription(sub)`, `remove_subscription(sub_id)`, `update_subscription(sub_id, updates)`, `get_subscription(sub_id)`

---

### YouTube Helpers

- **`resolve_youtube_channel(url_or_handle, status_cb)`** — Resolves a channel URL, `@handle`, or username to a channel ID using yt-dlp (`extract_flat=True`, `playlist_items="1"`). No YouTube API key required. Returns channel ID string or None.

- **`_fetch_youtube_rss(channel_id)`** — Fetches YouTube's public channel RSS feed (`youtube.com/feeds/videos.xml?channel_id=…`) via `urllib`. No API key required. Returns list of `{id, title, published, url, duration_seconds}` dicts (`duration_seconds` is None at this stage — filled in later if needed).

- **`_get_duration(video_url)`** — Fetches duration of a single video via yt-dlp. Called only for videos that pass other filters (to minimise yt-dlp requests). Returns seconds as int, or None on failure.

---

### RSS / Substack Helpers

- **`_to_rss_url(sub_type, url)`** — Converts a Substack homepage or post URL to its RSS feed URL (`base/feed`). Generic RSS URLs passed through unchanged.

- **`_fetch_rss(feed_url)`** — Fetches and parses an RSS feed via `feedparser`. Returns list of `{id, title, published, url, content}` dicts. Prefers `content[0].value` over `summary` for body text.

---

### Content Fetching

**`_fetch_content(item, sub_type, config, log)`** — Fetches text content for a single feed item. Returns `(content_text, entries, doc_title)`.

**YouTube strategy (4 levels, in order):**
1. **yt-dlp subtitle download** (primary in subscription context — avoids rate-limiting issues with `youtube_transcript_api`)
2. **`youtube_transcript_api` without cookies**
3. **`youtube_transcript_api` with browser cookies**
4. **Audio transcription** via `audio_handler.transcribe_youtube_audio()` as last resort

**Substack / RSS strategy (3 levels):**
1. **RSS entry body** — uses `content` field already in the feed item (no extra HTTP call; requires content length > 200 chars)
2. **`substack_updates.fetch_substack_content(url)`** — dedicated full-article fetch (Substack only)
3. **Generic HTTP fetch** — plain `urllib` GET + strip HTML tags (fallback for any URL type)

**VTT caption parsing:**
- `_fetch_captions_via_ytdlp(url, fallback_title, log)` — downloads `.vtt` subtitle file to a temp dir via yt-dlp. Deduplicates consecutive identical lines. Returns `(success, entries, title)`.
- `_parse_vtt(vtt_path)` — parses VTT blocks into DocAnalyser entry dicts `{text, start, timestamp_label}`. Strips VTT inline tags, deduplicates, converts timestamps to seconds.
- `_vtt_time_to_seconds(ts)` — handles both `HH:MM:SS.mmm` and `MM:SS.mmm` formats.

---

### AI Processing & Library Save

**`_run_ai_and_save(item, sub, content_text, entries, doc_title, config, log)`** — Calls the AI provider with the subscription's prompt then saves the results. Returns True on success.

1. Resolves provider/model/key from `config` (falls back to `DEFAULT_MODELS` if no model set)
2. Builds a single-turn `messages` list: `[{role: "user", content: "{prompt}\n\n---\n\n{content}"}]`
3. Calls `ai_handler.call_ai_provider()`
4. Saves source document via `document_library.add_document_to_library()` with subscription metadata
5. Saves AI output via `document_library.add_processed_output_to_document()`

> **Note:** On content fetch failure, the item is **not** added to `seen_guids` — it will be retried on the next check. On AI/save failure the same applies. Items are only marked as seen on full success.

**`_extract_interviewee(content_text, provider, model, api_key, doc_title="", host_name="")`** — Lightweight AI call that identifies the interviewee/guest from the opening of a YouTube transcript. Returns an empty string on failure so callers can treat the result as optional enrichment. Called by `_run_ai_and_save` only when `sub_type == "youtube_channel"`.

- **April 2026 — widened window and added context:** the content window was expanded from 800 characters to 5000 characters (~800 words) to cover transcripts where the guest introduction falls after a cold open, ads, or sponsor read. The prompt now also includes the document title and the subscription name (host) as context, so the AI can distinguish host from guest reliably — e.g. *"Host / channel name: Daniel Davis; do not return that name"*. The host-name signal is the reliable workhorse (always present); the title is a bonus when it happens to name the guest.
- When extraction succeeds, the interviewee name is stored on **both** the source document's metadata and the AI response document's metadata (key: `interviewee`), so the Thread Viewer's metadata block renders it regardless of which doc is opened. When it fails, the key is absent on the source doc and empty on the response doc.

---

### Check Entry Points

**`check_subscription(sub, config, status_cb, item_done_cb, stop_flag)`** — Checks one subscription:
1. Fetches feed items (`_fetch_youtube_rss` or `_fetch_rss`)
2. Filters to unseen items (not in `seen_guids`)
3. Filters by `look_back_hours` window (parses RFC 2822 / ISO 8601 published dates)
4. For each new item: duration check (YouTube only) → fetch content → AI + save
5. Returns `{processed, skipped, errors, new_seen_guids}`

> **Caller is responsible** for persisting `new_seen_guids` and updating `last_checked` — `check_subscription` does not write to disk itself.

**`check_all_subscriptions(config, status_cb, item_done_cb, sub_done_cb, stop_flag)`** — Iterates all enabled subscriptions, calls `check_subscription` for each, persists `seen_guids` and `last_checked` after each one, accumulates totals. Supports mid-run cancellation via `stop_flag[0] = True`.

---

## subscription_dialog.py (~650 lines)
**Purpose:** Tkinter dialog for managing subscriptions and triggering manual checks.

**Entry Point:** `open_subscriptions_dialog(parent, app)` — creates and returns a `SubscriptionDialog` instance.

**Called By:** `Main.py` (`open_subscriptions_dialog`)

---

### Layout

```
┌──────────────────────────────────────────────────────────────────┐
│ [Subscriptions list]  │  [Detail / edit panel]                   │
│                       │                                          │
│ [Add][Remove][Rename] │                          [Save Changes]  │
│ [Duplicate][Reset History]                                       │
├───────────────────────┴──────────────────────────────────────────┤
│  [Check All Now]  [Check Selected]  [Cancel Check]  ██░ status   │
└──────────────────────────────────────────────────────────────────┘
```

---

### Class: SubscriptionDialog

**Left panel — subscription list:**
- `tk.Listbox` (single-select) showing subscription names; disabled subscriptions suffixed with `[off]`
- **Add** — creates a new subscription with `default_subscription()`, immediately prompts for a name via inline rename dialog
- **Remove** — confirms then deletes; does not affect already-processed library documents
- **Rename** — small `Toplevel` dialog; calls `_auto_save()` first to preserve current form state before reloading list
- **Duplicate** — deep copy with new ID, cleared `seen_guids` and `last_checked`
- **Reset History** — clears `seen_guids` and `last_checked` for the selected subscription so all recent items are reprocessed on the next check; shows confirmation with item count

**Right panel — detail/edit form:**

| Field | Widget | Notes |
|---|---|---|
| Name | Entry | Editable display name |
| Type | Combobox (readonly) | YouTube Channel / Substack Publication / RSS Feed |
| URL | Entry + Resolve button | Resolve triggers `resolve_youtube_channel()` in background thread; disabled for non-YouTube types |
| Channel ID | Entry (readonly) | Auto-filled by Resolve; hidden for non-YouTube types |
| Min duration | Spinbox (0–300) | Minutes; 0 = no filter; disabled for non-YouTube types |
| Look back | Spinbox (0–8760) | Hours; 0 = all new since last check |
| Prompt | Combobox + Prompts Library button | Selecting from combo auto-loads prompt text |
| Prompt text | Text widget (6 rows) | Editable; loaded from prompt selection or manually typed |
| Enabled | Checkbutton | Controls inclusion in Check All |
| Last checked | Label (read-only) | Formatted datetime or "Never" |
| Scheduling | LabelFrame (disabled) | Reserved for future use; always shown but controls disabled |

**Prompt selection strategies** (tried in order in `_open_prompts_library`):
1. `prompt_tree_manager.open_prompt_tree_for_selection()` — dedicated selection function if available
2. Hijack `app.set_prompt_from_library` callback and call `app.open_prompt_manager()`
3. Refresh the combo dropdown and ask user to select from it (fallback)

**Save / auto-save:**
- **Save Changes** button — validates, updates `self._subs[idx]` in memory, writes whole list via `save_subscriptions()`, refreshes listbox label
- **`_auto_save()`** — silent save called before any operation that reloads the list (Rename, Duplicate, Check Now), to prevent unsaved form values being lost

**List-select guard:** `_on_list_select` ignores spurious empty-selection events (fired when the prompt combobox steals focus) and no-ops when the same index is re-clicked, preventing the form from being wiped mid-edit.

---

### Check Now (background thread)

- **Check All Now** — loads all enabled subscriptions from disk, runs `check_all_subscriptions()` in a daemon thread
- **Check Selected** — runs `check_subscription()` for the currently shown subscription only; persists `seen_guids` and `last_checked` on completion
- **Cancel Check** — sets `self._stop[0] = True`; `check_subscription` polls this flag between items

**Progress delivery:** background worker enqueues `(msg_type, payload)` tuples; `_poll_queue()` runs every 100ms on the main thread to drain the queue and update `status_var` and the progress bar. Message types: `status`, `item_done`, `resolve_done`, `done`.

**Close guard:** If a check is running, close prompts for confirmation before cancelling.

---

### Dependencies
- `subscription_manager` (all logic)
- `config_manager.load_prompts` (prompt combo population)
- `prompt_tree_manager.open_prompt_tree_for_selection` (optional — prompt picker)
- `tkinter`, `threading`, `queue`

---

## Known Issues / Status (April 2026)

- Feature is functional for manual "Check Now" use but has known bugs under active investigation.
- Scheduling (automatic periodic checks) is stubbed in the UI and data model but not yet implemented.
- `substack_updates.py`'s `fetch_substack_content()` references several helper functions (`extract_preloads_from_html`, `extract_substack_publication`, etc.) that are defined in the full `substack_utils.py` — the subscription Substack path depends on that integration being complete.
- The `_run_ai_and_save` function uses `call_ai_provider` — verify this function signature matches `ai_handler.py`'s current export before relying on it.
- Not yet wired into the main app menu (no button/menu item in `Main.py` calls `open_subscriptions_dialog` yet).

---

*Added: 13 April 2026*
