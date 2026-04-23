# DocAnalyser Subscriptions — Tree-Based Redesign Plan

**Date:** 21 April 2026
**Version:** 1.0
**Approach:** Tree-based UI and SQLite storage, reusing existing `tree_manager_base` framework and `folders`/`folder_items` schema.
**Scope:** Full replacement of the current flat-list subscription UI and JSON storage with a folder tree, per-folder defaults, drag-drop URL detection, digest routing, and scheduling v1.

---

## Prerequisites

Before starting Stage 1:

1. **Subscription stabilisation pass is complete** (bugs #1–#14 plus model-field placeholder, verified 20 April 2026). Starting from a solid baseline means this redesign can focus on new behaviour rather than fighting existing bugs.
2. **Back up** `%APPDATA%\DocAnalyser_Beta\subscriptions.json` if the existing subscriptions have any historical value. The migration path for this redesign **does not preserve existing subscriptions** by explicit user preference — they'll need to be re-added after Stage 2.
3. **Back up** `%APPDATA%\DocAnalyser_Beta\docanalyser.db` before Stage 1 so the schema change can be rolled back if needed.

---

## Guiding Principle

**Maximum reuse of existing infrastructure.** The `tree_manager_base.py` framework, the SQLite `folders` + `folder_items` tables, and the DB adapter pattern used for Prompts and Documents are already generic — they're parameterised by `library_type`. The subscription tree uses `library_type='subscriptions'` without any schema migration for the folder structure itself. Only subscription-specific data (URL, resolver, seen_guids, etc.) needs a new table.

---

## Architecture Overview

```
BEFORE (current):
  subscription_dialog.py (flat listbox UI)
       │
       ▼
  subscription_manager.py ──→ subscriptions.json

AFTER (this plan complete):
  subscription_tree_manager.py (tree UI, extends TreeManagerUI)
       │
       ▼
  subscription_manager.py (unchanged pipeline, reads via facade)
       │
       ▼
  subscription_db_adapter.py ──→ db_manager.py ──→ docanalyser.db
                                     │
                                     └─→ Tables:
                                          folders (library_type='subscriptions')
                                          folder_items
                                          subscriptions (NEW)
                                          subscription_folder_defaults (NEW)
```

`subscription_manager.py`'s pipeline (`check_subscription`, `_fetch_content`, `_run_ai_and_save`, `check_all_subscriptions`, `generate_digest`) is unchanged. Only `load_subscriptions()`/`save_subscriptions()` get rewired to read from SQLite. This keeps the stabilisation work intact.

---

## What Already Exists That We Build On

| Piece | File | Reuse |
|-------|------|-------|
| `TreeNode` abstract base class | `tree_manager_base.py` | Subclass for `SubscriptionItem` |
| `FolderNode` | `tree_manager_base.py` | Used as-is |
| `TreeManager` | `tree_manager_base.py` | Used as-is (already library-agnostic) |
| `TreeManagerUI` | `tree_manager_base.py` | Subclass for `SubscriptionTreeManagerUI`; gives drag-drop, context menu, keyboard shortcuts, rename/delete/move, cut/copy/paste, folder expansion, search |
| `folders` + `folder_items` tables | `db_manager.py` | `library_type='subscriptions'` — no schema change for folders |
| `db_create_folder`, `db_get_folder_tree`, `db_add_item_to_folder` | `db_manager.py` | Call directly |
| `prompt_db_adapter.py` pattern | — | Mirror for `subscription_db_adapter.py` |
| Working subscription pipeline | `subscription_manager.py` | Left alone — only data layer changes |

---

## New Files

| File | Purpose | Approx. size |
|------|---------|-------------|
| `subscription_tree_manager.py` | `SubscriptionItem` (TreeNode subclass) + `SubscriptionTreeManagerUI` | 600–800 lines |
| `subscription_db_adapter.py` | Serialise/deserialise subscription tree to SQLite | ~250 lines |
| `subscription_detectors/__init__.py` | Detector plugin registry | ~100 lines |
| `subscription_detectors/youtube.py` | YouTube channel detector | ~80 lines |
| `subscription_detectors/substack.py` | Substack detector | ~60 lines |
| `subscription_detectors/rss.py` | Generic RSS/Atom/JSON Feed detector with feed discovery | ~120 lines |
| `subscription_detectors/podcast.py` | iTunes podcast lookup detector | ~80 lines |

---

## Modified Files

| File | Change | Approx. net size |
|------|--------|-----------------|
| `db_manager.py` | Add `subscriptions` + `subscription_folder_defaults` schema + CRUD | +250 lines |
| `subscription_manager.py` | `load_subscriptions()` and friends go via SQLite adapter; check pipeline unchanged | +/- 100 lines |
| `subscription_dialog.py` | `open_subscriptions_dialog` instantiates the new tree UI instead of the flat dialog; existing dialog code retires | -900 lines (most of it deleted) |
| `Main.py` | No change — the entry point is already `open_subscriptions_dialog(root, app)` |

---

## Data Model

### Conceptual Shift

The current model has a YouTube-biased field (`channel_id`). The new model generalises:

- `source_type` — `youtube_channel`, `substack`, `rss`, `podcast`, extensible
- `source_url` — the URL the user originally provided (display only)
- `source_ref` — the type-specific stable resolver used for fetching:
  - YouTube: channel ID (`UCxxx…`)
  - Substack: feed URL
  - RSS: feed URL
  - Podcast: iTunes podcast ID

This answers the question "does a subscription need a channel ID?" cleanly: no, it needs a *resolver for its type*, and channel ID is the YouTube-flavoured resolver.

### Definition of a Subscription

A URL or input qualifies as a subscription if the detector can extract all four of:

1. A stable resolver (`source_ref`)
2. A detected source type (`source_type`)
3. A human-readable default name
4. A fetch strategy (which of the existing fetchers to call)

If any is missing, the detector raises `DetectionError` with a user-friendly message.

### Schema Additions

#### `subscriptions` table

```sql
CREATE TABLE IF NOT EXISTS subscriptions (
    id                      TEXT PRIMARY KEY,        -- 12-char hex
    name                    TEXT NOT NULL,
    source_type             TEXT NOT NULL,           -- youtube_channel | substack | rss | podcast
    source_url              TEXT NOT NULL,           -- original user-provided URL
    source_ref              TEXT NOT NULL,           -- type-specific resolver
    fetch_strategy          TEXT NOT NULL,           -- youtube_channel_feed | rss_feed | itunes_podcast_lookup
    enabled                 INTEGER NOT NULL DEFAULT 1,
    -- Per-item overrides; NULL = inherit from folder
    prompt_name             TEXT,
    prompt_text             TEXT,
    min_duration            INTEGER,
    look_back_hours         INTEGER,
    provider                TEXT,
    model                   TEXT,
    -- State (never inherited)
    last_checked            TEXT,
    seen_guids              TEXT,                    -- JSON array
    -- Scheduling
    schedule_enabled        INTEGER DEFAULT 0,
    check_interval_hours    INTEGER DEFAULT 6,
    -- Routing (for Documents Library mirroring, Stage 7)
    mirror_target_folder_id INTEGER REFERENCES folders(id),
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subscriptions_type ON subscriptions(source_type);
CREATE INDEX IF NOT EXISTS idx_subscriptions_enabled ON subscriptions(enabled);
```

#### `subscription_folder_defaults` table

```sql
CREATE TABLE IF NOT EXISTS subscription_folder_defaults (
    folder_id               INTEGER PRIMARY KEY REFERENCES folders(id) ON DELETE CASCADE,
    prompt_name             TEXT,
    prompt_text             TEXT,
    min_duration            INTEGER,
    look_back_hours         INTEGER,
    provider                TEXT,
    model                   TEXT,
    mirror_target_folder_id INTEGER REFERENCES folders(id),
    schedule_enabled        INTEGER,
    check_interval_hours    INTEGER
);
```

Separate table (Option B from design discussion) keeps the generic `folders` table free of library-specific columns. Adding additional folder-level default fields later is additive — no migration needed for existing folder rows.

### Inheritance Rules

When the subscription pipeline needs a field at check time, it resolves:

1. Subscription's own value (if non-NULL)
2. Nearest ancestor folder's default (walking up from leaf)
3. App-wide default (hardcoded or from config)

Inheritance runs at flatten time (Stage 4), so the existing `check_subscription` function sees a fully-populated sub dict and doesn't need to know about folders.

---

## Detector Architecture

Two layers: detectors (figure out what the input is) and fetchers (how to poll it).

### Detectors (pluggable)

Each detector implements:

```python
def matches(url: str) -> bool:
    """Quick URL pattern check — cheap, no network."""

def resolve(url: str) -> SubscriptionRecord:
    """
    Do deeper inspection and return a populated SubscriptionRecord
    with (source_type, source_ref, default_name, fetch_strategy,
    metadata). Raise DetectionError if this detector matched on
    pattern but the deeper resolution failed (so the registry can
    move on to the next detector).
    """
```

Registry tries detectors in priority order. First successful `resolve()` wins. If none match, a final fallback raises `DetectionError` with a helpful message.

### Fetchers (small, shared set)

- `youtube_channel_feed` — existing `_fetch_youtube_rss` logic (channel RSS → uploads-playlist RSS → yt-dlp fallback)
- `rss_feed` — generic feedparser wrapper (handles RSS, Atom, JSON Feed)
- `itunes_podcast_lookup` — existing ABC Listen pattern (iTunes API reconfirms RSS URL, then `rss_feed`)

Check-time dispatch switches on `fetch_strategy`, not `source_type`. Adding a new source type (Mastodon, Reddit, etc.) typically means adding a detector that sets `fetch_strategy='rss_feed'` — no new fetcher needed.

### Detector Error Cases

Detector failures surface these user-facing messages:

- **Plain article URL** → "This looks like a single article. Subscribe to its publication instead — try the publication's homepage URL."
- **YouTube video URL** (one-off) → auto-resolves upward to the uploading channel. Success, not error.
- **Local document file** → "Subscriptions are for remote feeds. This file would make more sense in the Documents Library."
- **`.url` shortcut file** → unwrap to the URL inside, re-run detection.
- **Bare domain, no feed found** → "No feed found at this address. If you know the feed URL, try pasting it directly."
- **Unreachable URL** → "Could not reach this URL. Check the address or your connection."
- **Unrecognised** → "Could not determine subscription type. Supported sources are YouTube channels, Substack publications, podcasts, and RSS feeds."

---

## Build Order

Each stage ends in a testable outcome. Checkpoints flagged are where the feature is fully usable on the new stack — safe stopping points if work is interrupted.

### Stage 1 — Schema and Data Layer

- Add `subscriptions` and `subscription_folder_defaults` tables to `db_manager.py`
- Add CRUD functions: `db_add_subscription`, `db_get_subscription`, `db_update_subscription`, `db_delete_subscription`, `db_get_all_subscriptions`, `db_set_folder_defaults`, `db_get_folder_defaults`
- Unit tests following the existing `test_stage_c.py` style

**Testable outcome:** tests pass. No UI change. Existing flat JSON subscriptions still work (untouched).

### Stage 2 — Wipe and Fresh Start

- Add a `db_init_subscription_tables()` call on first startup that creates the two new tables
- Existing `subscriptions.json` is renamed to `.pre_tree_redesign` for safety but not migrated (per user decision)
- Subscriptions dialog on first post-upgrade launch shows an empty tree

**Testable outcome:** first launch after upgrade, existing subscriptions file is archived, tables exist, no data in them. The current (pre-redesign) dialog still loads — it just sees an empty list.

### Stage 3 — `SubscriptionItem` and Adapter

- Create `subscription_tree_manager.py` with `SubscriptionItem(TreeNode)` class
- Create `subscription_db_adapter.py` with `load_subscription_tree_from_sqlite()` and `save_subscription_tree_to_sqlite()` following the `prompt_db_adapter.py` pattern
- A small script or unit test inserts subs, creates folders, moves things, saves, reloads, and verifies round-trip

**Testable outcome:** tree can be manipulated in memory and persisted. No new UI yet.

### Stage 4 — Facade Layer — CHECKPOINT

- Replace internals of `load_subscriptions()` and `save_subscriptions()` in `subscription_manager.py` to read/write via the SQLite adapter, keeping signatures identical
- Flatten the tree for check-time callers (existing check pipeline doesn't know about folders)
- Folder defaults resolved into sub dicts during flatten
- Check pipeline unchanged

**Testable outcome:** existing Subscriptions dialog works identically, but data is now in SQLite. This is the safety milestone — if later stages go wrong, rollback to here still leaves a working feature.

### Stage 5 — Tree UI MVP (with Detectors) — CHECKPOINT

- Build `SubscriptionTreeManagerUI(TreeManagerUI)` with:
  - Tree view on the left (drag-drop, folders, sort, search — all inherited)
  - Detail panel on the right: Name, URL (drop target), detected type (read-only display), Min Duration, Look Back, Prompt, Enabled
  - Check All / Check Selected / Generate Digest / Cancel buttons at the bottom
  - `View Log…` button retained
- Re-wire `open_subscriptions_dialog` to instantiate the new UI
- Implement four detectors + plain-URL fallback (YouTube, Substack, RSS, podcast)
- URL field: drag-drop or paste triggers `detect_subscription_type()` (debounced)
- Detected metadata populates the form automatically; detection errors shown inline below the URL field

**Testable outcome:** new tree UI fully functional. User can drag URLs in, organise into folders, run checks. No user-visible Type dropdown.

### Stage 6 — Per-folder and Per-item Defaults with Inheritance

- When a folder is selected in the tree, the right pane switches to "Folder defaults" editor: prompt, min duration, look back, provider, model
- Per-subscription form gets `(Inherit from folder)` as an option in each inheritable field
- Inheritance resolution (Stage 4) now does real work
- UI indicates which fields are inherited (italic grey text, or an icon)

**Testable outcome:** "Geopolitics" folder has one prompt. All three child subs display "(Inherit from folder)" for prompt. Overriding one child's prompt works without affecting siblings.

### Stage 7 — Auto-resolution Extras and Digest Routing

- URL detection handles: channel URL → channel ID, single-video URL → parent channel (via `resolve_youtube_channel`), Substack post URL → publication feed, `.url` shortcut unwrapping
- Digest destination logic:
  - Selections all within one subscription folder → digest saved to `Documents Library/<mirror path>/Digests/` (or root `Documents Library/Digests/` if no mirror set)
  - Selections span multiple folders → digest saved to `Documents Library/Digests/` at root
- If the Documents Library folder doesn't exist, it's created on first save

**Testable outcome:** URL-paste workflow covers the common cases. Digests land in the expected Documents Library folder.

### Stage 8 — Scheduling v1

- Global "check every N hours" setting (Settings → Subscriptions)
- Per-folder "exclude from scheduled checks" toggle on the folder defaults pane
- Background thread running on a timer; checks what's due and invokes the existing pipeline
- Status bar in the tree UI shows last-run timestamp and next-run estimate

**Testable outcome:** scheduled checks fire when expected, subject to exclusions; manual Check All/Check Selected still works; scheduling can be disabled entirely by setting the interval to 0.

---

## Risk Assessment

| Stage | Risk | Mitigation |
|-------|------|-----------|
| 1 | Schema mistake baked in | Unit tests per CRUD function before moving on |
| 2 | Existing data loss (noted — user accepted this) | Rename `.json` → `.pre_tree_redesign`, don't delete |
| 3 | Adapter round-trip bugs | Script-driven round-trip tests before UI work |
| 4 | Facade subtly changes behaviour | Run the existing stabilisation test plan (bugs #1, #3, #4, #11, #14) against the facade |
| 5 | User confusion with new UI | Keep Check All / Check Selected / Generate Digest buttons in familiar positions |
| 6 | Inheritance logic bugs | Separate test harness — populate various folder-override combinations, assert flatten produces expected sub dicts |
| 7 | Digest routing edge cases | Dry-run mode that prints intended save location without writing |
| 8 | Scheduler interference with manual checks | Single global lock: manual check cancels any in-progress scheduled check |

Stages 1–4 are reversible without user-visible consequences. Stage 5 is the first user-visible cutover and the highest-risk single stage. Stages 6–8 are additive on top of a working system.

---

## Out of Scope

Captured for later — not addressed in this plan:

- **Subscribers / recipients list** for auto-sending digests via email. The `SendDigestDialog` class in the current code is a starting point but a persistent recipient management feature deserves its own project.
- **Import/export** of subscription tree (parallel to prompt import/export) — useful for sharing subscription configs between machines, but defer.
- **Per-subscription content-type detection at check time** (e.g. a Substack post that happens to contain a podcast episode) — useful later but orthogonal to the tree redesign.

---

## Estimated Total

- **New code:** 1500–1800 lines
- **Changed code:** ~300 lines net
- **Deleted code:** ~900 lines (the current flat subscription dialog, less what's reused in the new detail panel)
- **Sessions:** 8 (one per stage, assuming no significant scope-creep)

---

## Reference Documents

- `Documentation/docanalyser_sqlite_schema.md` — current schema (this plan extends it)
- `Documentation/SQLite_Phase1_Implementation_Plan.md` — migration pattern (this plan follows its facade approach)
- `tree_manager_base.py` — the reusable tree framework (inspect before Stage 5)
- `prompt_tree_manager.py`, `document_tree_manager.py` — worked examples of the pattern we're following
