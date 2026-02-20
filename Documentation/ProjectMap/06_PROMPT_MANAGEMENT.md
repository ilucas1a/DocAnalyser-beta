# Project Map: Prompt Management

## prompt_manager.py (~250 lines)
- **Purpose:** Legacy Prompt Library dialog — flat list view for managing prompts
- **Pattern:** Module-level function `open_prompt_manager_window()` creates a Toplevel dialog
- **Dependencies:** tkinter, context_help
- **Called By:** settings_manager.py (fallback if prompt_tree_manager unavailable)
- **Status:** Superseded by prompt_tree_manager.py but kept for backwards compatibility

### Key Function:
- `open_prompt_manager_window(parent, prompts, prompts_path, save_func, refresh_callback, config, save_config_func)`
  - Listbox-based prompt selector with search (Name/Content/Both)
  - Edit prompt name and text
  - Add / Delete / Save / Set as Default / Close buttons
  - Visual feedback: green highlight on currently-editing prompt

---

## prompt_dropdown_builder.py (~230 lines)
- **Purpose:** Builds hierarchical dropdown lists for the main window's prompt selector
- **Pattern:** Pure functions, no UI — returns formatted dropdown lists + lookup dictionaries
- **Dependencies:** None (typing only)
- **Called By:** settings_manager.py (`refresh_main_prompt_combo`)

### Key Functions:
- `build_hierarchical_dropdown(prompts)` → (list, dict) — flat list format
  - Groups prompts by folder, favorites at top with ⭐ section
  - Returns: dropdown display strings + name→prompt mapping
- `build_hierarchical_dropdown_from_tree(tree_dict)` → (list, dict) — tree format (v2.0)
- `build_dropdown_auto(data)` → (list, dict) — **auto-detects format** (list or tree dict)
- `extract_prompt_name(display_name)` → str — strips icons/indent from dropdown entry
- `is_separator(entry)` → bool — checks for ─── separator lines
- `is_header(entry)` → bool — checks for ⭐ FAVORITES or 📁 folder headers
- `find_prompt_in_list(prompt_name, prompts)` → dict or None

### Dropdown Format:
```
⭐ FAVORITES
  ⭐ Counter arguments
  ⭐ Summary (200 words)
──────────────────────────────
📁 General
  Short 3-bullet summary
  Detailed dotpoints
──────────────────────────────
📁 Analysis
  Distill and evaluate
```

---

## prompt_tree_manager.py (~900+ lines)
- **Purpose:** Tree-structured Prompts Library with drag-drop, version control, favorites
- **Pattern:** Extends `TreeManagerUI` from tree_manager_base.py
- **Dependencies:** tkinter, tree_manager_base, context_help, json
- **Called By:** settings_manager.py (`open_prompt_manager`)

### Class: PromptVersion
- Single version snapshot: text, timestamp, note, is_default, is_system, user_modified
- `to_dict()` / `from_dict()` — serialization

### Class: PromptItem (extends TreeNode)
- **Version control:** up to 10 versions per prompt, with save/restore
- **Favorites:** `toggle_favorite()` / `set_favorite()`
- **Key Methods:**
  - `get_current_text()` → str
  - `save_new_version(text, note)` — creates new version, trims old ones
  - `restore_version(index)` / `restore_default()` — version navigation
  - `is_modified_from_default()` → bool — checks if system prompt was changed

### Class: PromptTreeManagerUI (extends TreeManagerUI)
- 4-level folder hierarchy with drag-and-drop
- Preview/edit panel on right side
- **Edit Mode:** protects keyboard shortcuts (Delete, F2, Ctrl+X/C/V) when editing text
- **Key Methods:**
  - `show_prompt_preview(prompt)` — displays in preview pane
  - `enter_edit_mode()` / `exit_edit_mode(save)` — toggle editing with undo support
  - `save_current_edit()` — saves version + persists to disk
  - `show_version_history()` — modal dialog showing all versions with restore
  - `toggle_favorite_status()` — star/unstar prompt
  - `restore_default()` — revert system prompt to original
  - `use_prompt()` — loads prompt into main window via callback
  - `save_tree(show_message)` — saves entire tree to prompts.json (atomic write)

### Module Functions:
- `load_prompts_from_file(filepath)` → list — loads and flattens tree format for backwards compat
- `open_prompt_tree_manager(parent, prompts, ...)` — **main entry point**, creates window
- `open_prompt_manager_window(...)` — backwards compatibility alias

### File Format (prompts.json):
- **Version 2.0 (current):** `{"version": "2.0", "root_folders": {...}}` — tree with nested PromptItem nodes
- **Legacy flat format:** `[{"name": "...", "text": "..."}]` — auto-migrated on first open
