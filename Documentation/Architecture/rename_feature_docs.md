# Prompts Library Rename Feature

**Updated:** prompt_tree_manager.py  
**New Feature:** Rename folders and prompts  
**Date:** January 11, 2026

---

## What's New

### ✅ Three Ways to Rename:

**1. Rename Button** (📍 Top left of tree)
- Select any folder or prompt
- Click "✏️ Rename" button
- Enter new name
- Done!

**2. F2 Keyboard Shortcut** (⌨️ Fastest!)
- Select any folder or prompt
- Press **F2**
- Enter new name
- Press Enter

**3. Right-Click Context Menu** (🖱️ Most intuitive)
- Right-click any folder or prompt
- Select "✏️ Rename"
- Enter new name
- Done!

---

## How It Works

### Rename Dialog Features:

**📋 Shows Current Name**
```
Current name: Summary, dot points, concise
New name: [Summary - Brief and Concise]
```

**✓ Smart Validation:**
- Can't use empty names
- Can't duplicate names in same folder
- Shows clear error messages

**⌨️ Keyboard Friendly:**
- Enter key → Rename
- Escape key → Cancel
- Text is pre-selected for easy editing

---

## Usage Examples

### Example 1: Rename a Folder
```
1. Select "General" folder
2. Press F2
3. Type "My Prompts"
4. Press Enter
→ ✓ Folder renamed!
```

### Example 2: Rename a Prompt
```
1. Right-click "Summary, dot points, concise"
2. Select "✏️ Rename"
3. Type "Quick Summary"
4. Click "✓ Rename"
→ ✓ Prompt renamed!
```

### Example 3: Organize Your Library
```
Before:
📁 General
   📄 Summary, dot points, concise
   📄 Summary (200 words, paragraphs)
   📄 Counter arguments

After (rename folder):
📁 Document Summaries
   📄 Summary, dot points, concise
   📄 Summary (200 words, paragraphs)
   📄 Counter arguments
```

---

## Context Menu Features

**Right-click any item for quick access:**

```
✏️ Rename          ← New!
🗑️ Delete
─────────────────
⊕ New Folder
⊕ New Prompt
```

**Smart Selection:**
- Right-clicking automatically selects the item
- Context menu shows relevant options
- Works anywhere in the tree

---

## UI Changes

### Before:
```
[⊕ New Folder] [⊕ New Prompt]
```

### After:
```
[⊕ New Folder] [⊕ New Prompt] [✏️ Rename]
```

**Rename button:**
- Disabled when nothing selected
- Enabled for folders (any time)
- Enabled for prompts (any time)

---

## Technical Details

### Validation Rules:

**Folder Rename:**
- Must be unique among root folders
- Can't be empty
- Same name = no action (just closes dialog)

**Prompt Rename:**
- Must be unique within parent folder
- Can't be empty
- Same name = no action (just closes dialog)
- Prompts in different folders can have same name ✓

### Data Preservation:

**When renaming folders:**
- All prompts inside remain intact
- All subfolders remain intact (if any)
- Folder expanded/collapsed state preserved

**When renaming prompts:**
- All version history preserved
- "Last used" date preserved
- System/User status preserved
- Current version remains current

---

## Keyboard Shortcuts Summary

| **Key** | **Action** |
|---------|------------|
| F2 | Rename selected item |
| Enter (in dialog) | Confirm rename |
| Escape (in dialog) | Cancel rename |
| Right-click | Show context menu |

---

## Error Messages

### "Name cannot be empty"
**Cause:** Tried to rename to blank/whitespace  
**Solution:** Enter a valid name

### "A folder named 'X' already exists"
**Cause:** Tried to rename folder to existing folder name  
**Solution:** Choose a different name

### "A prompt named 'X' already exists in folder 'Y'"
**Cause:** Tried to rename prompt to existing prompt name in same folder  
**Solution:** Choose a different name, or move to different folder first

---

## Integration with Existing Features

### ✅ Works With:

**Version History:**
- Rename doesn't affect version history
- All versions preserved with new name

**Edit Mode:**
- Can rename while viewing a prompt
- Preview updates automatically after rename

**Unsaved Changes:**
- Rename marks changes as unsaved
- Warning shown on close if not saved

**Save All:**
- Renamed items saved when clicking "💾 Save All Changes"
- Persists across sessions

---

## Best Practices

### 📝 Organizing Your Prompts:

**1. Use Descriptive Names:**
```
❌ "Summary"
✓ "Document Summary - Concise"

❌ "Analysis"
✓ "Critical Analysis with Arguments"
```

**2. Use Consistent Naming:**
```
✓ "Summary - Brief"
✓ "Summary - Detailed"
✓ "Summary - With Quotes"
```

**3. Organize by Purpose:**
```
📁 Document Analysis
   📄 Summary - Brief
   📄 Summary - Detailed
   📄 Extract Key Points
   
📁 Writing Tools
   📄 Proofread for Errors
   📄 Improve Clarity
   📄ify Tone
```

---

## Testing Checklist

After updating, test these scenarios:

### Folder Rename:
- [ ] Select folder, click Rename button
- [ ] Select folder, press F2
- [ ] Right-click folder, select Rename
- [ ] Try empty name (should error)
- [ ] Try duplicate name (should error)
- [ ] Rename successfully
- [ ] Verify all prompts inside still work

### Prompt Rename:
- [ ] Select prompt, click Rename button
- [ ] Select prompt, press F2
- [ ] Right-click prompt, select Rename
- [ ] Try empty name (should error)
- [ ] Try duplicate name in same folder (should error)
- [ ] Rename successfully
- [ ] Open History - version history should be intact
- [ ] Edit prompt - should work with new name

### Context Menu:
- [ ] Right-click empty space (no selection)
- [ ] Right-click folder
- [ ] Right-click prompt
- [ ] Select "Rename" from menu
- [ ] Select "Delete" from menu
- [ ] Select "New Folder" from menu
- [ ] Select "New Prompt" from menu

### Keyboard Shortcuts:
- [ ] F2 with folder selected
- [ ] F2 with prompt selected
- [ ] F2 with nothing selected (should do nothing)
- [ ] Enter in rename dialog (should rename)
- [ ] Escape in rename dialog (should cancel)

---

## Troubleshooting

### Q: Rename button is greyed out
**A:** Select a folder or prompt first. Button enables when item is selected.

### Q: F2 doesn't work
**A:** Make sure tree view has focus. Click on tree first, then press F2.

### Q: Right-click shows wrong menu
**A:** This is the tree's context menu. Make sure to right-click directly on an item.

### Q: After rename, prompt content is gone
**A:** This shouldn't happen - rename preserves all data. If it does:
1. Don't click "Save All"
2. Close prompts library
3. Reopen - should be restored
4. Report bug!

---

## File Changes

**Modified:** prompt_tree_manager.py  
**Lines added:** ~120  
**New function:** `rename_item()`  
**UI changes:** Added rename button, F2 shortcut, right-click menu  

**Backwards compatible:** Yes ✓  
**Breaks existing code:** No ✓  
**Requires Main.py update:** No ✓  

---

## Summary

**You can now:**
- ✅ Rename any folder or prompt
- ✅ Use F2 for quick rename
- ✅ Right-click for context menu
- ✅ Organize your library better
- ✅ Fix typos in names easily
- ✅ All version history preserved

**Three ways to rename:**
1. Click "✏️ Rename" button
2. Press F2 key
3. Right-click → "✏️ Rename"

**Simple and intuitive!** 🎯
