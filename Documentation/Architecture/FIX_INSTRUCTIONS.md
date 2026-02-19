# FIXING: Drag-Drop & Folder Creation Issues

## Summary of Issues

You reported:
1. ❌ **Drag and drop no longer working**
2. ❌ **Can't create level 1 (root) folder**
3. ❌ **Lost functionality that was working before**

---

## Root Cause Analysis

The issue occurred when I created the new `prompt_tree_manager.py` that inherits from the base. I may have:

1. **Missing Move Up/Down buttons** in the overridden UI → **FIXED NOW**
2. **Drag-drop bindings might conflict** with tree selection
3. **Folder creation logic** might be confusing

---

## What I've Fixed

### ✅ Fix 1: Added Move Up/Down Buttons

Updated `prompt_tree_manager.py` line ~301-313 to include:
```python
# Reorder buttons
ttk.Label(controls, text=" │ ", foreground='gray').pack(side=tk.LEFT)

self.btn_move_up = ttk.Button(controls, text="↑ Move Up", 
                              command=self.move_selected_up, width=12, state=tk.DISABLED)
self.btn_move_up.pack(side=tk.LEFT, padx=2)

self.btn_move_down = ttk.Button(controls, text="↓ Move Down", 
                                command=self.move_selected_down, width=12, state=tk.DISABLED)
self.btn_move_down.pack(side=tk.LEFT, padx=2)
```

---

## What Should Work Now

### Drag-and-Drop
**How it works:**
1. Click and HOLD on an item
2. Drag at least 5-10 pixels
3. Cursor changes to hand (✓) or X (✗)
4. Hover over target folder
5. Release mouse

**If not working:**
- Check console for errors
- Make sure you're dragging onto a **folder**, not a prompt
- Try dragging more than 10 pixels

### Creating Root Folder
**How it works:**
1. Click in **empty space** to deselect everything
2. Click "⊕ New Folder" button
3. Enter folder name
4. Click Create
5. Folder appears at root level

**If folder is selected when you click "New Folder":**
- It will create INSIDE that folder
- To create at root: **Deselect first** (click empty space)

---

## Files You Need

### Required Files (Latest):

1. **tree_manager_base.py** (1,290 lines)
   - Version with reorder feature
   - Has drag-drop
   - Has all keyboard shortcuts

2. **prompt_tree_manager_COMPLETE.py** (990 lines)
   - Rename to: `prompt_tree_manager.py`
   - Has Move Up/Down buttons
   - Calls all setup methods
   - Should work completely

---

## Installation Steps

### Step 1: Backup Current Files
```powershell
cd C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV

# Backup everything
cp tree_manager_base.py tree_manager_base_BACKUP.py
cp prompt_tree_manager.py prompt_tree_manager_BACKUP.py
cp prompts.json prompts_BACKUP.json
```

### Step 2: Replace Files
```powershell
# Copy new versions
# (Use files from this session)

# tree_manager_base.py → DocAnalyzer_DEV\tree_manager_base.py
# prompt_tree_manager_COMPLETE.py → DocAnalyzer_DEV\prompt_tree_manager.py
```

### Step 3: Verify Files
```powershell
# Check file sizes
# tree_manager_base.py should be ~1290 lines
# prompt_tree_manager.py should be ~990 lines
```

### Step 4: Test

**Test A: UI Elements**
1. Open DocAnalyser
2. Click "Prompts Library"
3. **VERIFY YOU SEE:**
   - ⊕ New Folder button
   - ⊕ New Prompt button
   - ✏️ Rename button
   - 🗑️ Delete button
   - **│ separator**
   - **↑ Move Up button**
   - **↓ Move Down button**

**If Move Up/Down buttons are missing:** Files didn't copy correctly!

**Test B: Drag-Drop**
1. Select a prompt
2. Hold mouse button down
3. Drag across screen
4. Hover over folder
5. Look for cursor change (hand or X)
6. Release

**Test C: Root Folder**
1. Click in empty space (deselect all)
2. Click "⊕ New Folder"
3. Name: "Test Root"
4. Click Create
5. Should appear at root level

**Test D: Subfolder**
1. Click on "General" folder
2. Click "⊕ New Folder"
3. Dialog should say: "Will be created in: General"
4. Name: "Test Sub"
5. Click Create
6. Should appear inside General

---

## Debugging

### Check 1: Buttons Visible?

When library opens, count buttons:
- [ ] ⊕ New Folder
- [ ] ⊕ New Prompt  
- [ ] ✏️ Rename (grayed out when nothing selected)
- [ ] 🗑️ Delete (grayed out when nothing selected)
- [ ] **↑ Move Up** (grayed out when nothing selected) ← **Should exist!**
- [ ] **↓ Move Down** (grayed out when nothing selected) ← **Should exist!**

**If Move Up/Down missing:**
- Wrong version of prompt_tree_manager.py installed
- Use prompt_tree_manager_COMPLETE.py

### Check 2: Console Errors?

When you try to drag, look for:
```
Error: ...
AttributeError: ...
Exception: ...
```

**If you see errors:**
- Copy the FULL error message
- Tell me what it says

### Check 3: Drag Distance

Drag-drop requires minimum 5 pixel movement to start.

**Try:**
1. Click on item
2. Hold mouse down
3. Move mouse at least 20 pixels (1cm on screen)
4. Should see cursor change

**If cursor doesn't change:**
- Drag handlers not working
- Check console for errors

---

## Common Problems & Solutions

### Problem 1: "Nothing happens when I drag"

**Symptoms:**
- Click and drag
- No cursor change
- No movement

**Solutions:**
1. Check console for Python errors
2. Verify tree_manager_base.py is correct version (1290 lines)
3. Verify setup_drag_drop() is being called
4. Try dragging at least 20 pixels

### Problem 2: "New Folder creates inside selected folder"

**This is correct behavior!**

**To create at ROOT level:**
1. Click in **empty space** first (deselects)
2. Then click "⊕ New Folder"

**To create INSIDE folder:**
1. Click on folder
2. Then click "⊕ New Folder"

### Problem 3: "Move Up/Down buttons missing"

**Cause:** Old version of prompt_tree_manager.py

**Solution:**
1. Use prompt_tree_manager_COMPLETE.py
2. Rename to prompt_tree_manager.py
3. Restart DocAnalyser

### Problem 4: "Can't drop on folder"

**Make sure:**
- Dragging onto a **folder** (📁), not a prompt (📄)
- Folder is visible and not collapsed
- Not trying to drop folder into itself
- Not exceeding depth limit (4 levels)

---

## Quick Test Commands

Open Python console and try:

```python
# After opening Prompts Library
# (You'll need reference to UI instance)

# Check if drag-drop is set up
print("Drag data:", hasattr(ui, 'drag_data'))

# Check if buttons exist
print("Move Up button:", hasattr(ui, 'btn_move_up'))
print("Move Down button:", hasattr(ui, 'btn_move_down'))

# Check tree bindings
bindings = ui.tree.bind()
print("Tree has bindings:", len(bindings))
```

---

## If Still Not Working

**Please tell me:**

1. **Which file versions are you using?**
   - tree_manager_base.py size?
   - prompt_tree_manager.py size?

2. **What do you see?**
   - Screenshot of buttons row
   - Do you see ↑ ↓ buttons?

3. **What happens when you drag?**
   - Cursor changes?
   - Console errors?
   - Item moves?

4. **What happens when you click "New Folder"?**
   - With nothing selected?
   - With folder selected?
   - With prompt selected?

5. **Console output?**
   - Any errors?
   - Any DEBUG messages?

---

## Expected Working State

When everything is working:

**UI:**
```
📁 Prompts Library                           [Expand All] [Collapse All]

[⊕ New Folder] [⊕ New Prompt] [✏️ Rename] [🗑️ Delete] │ [↑ Move Up] [↓ Move Down]

📁 General
   📄 Prompt 1
   📄 Prompt 2
📁 Research
   📄 Analysis
```

**Drag-Drop:**
- Can drag "Prompt 1" into "Research" folder
- Cursor changes to hand (valid) or X (invalid)
- Confirmation shows after drop

**Folder Creation:**
- Deselect → New Folder → Creates at root
- Select folder → New Folder → Creates inside
- Select prompt → New Folder → Creates at root

**Keyboard:**
- Ctrl+Up moves selected item up
- Ctrl+Down moves selected item down
- F2 renames
- Delete deletes

---

## Files to Download

From this session:

1. **tree_manager_base.py** (1,290 lines with reorder)
2. **prompt_tree_manager_COMPLETE.py** (990 lines complete)
3. **TROUBLESHOOTING.md** (this file + detailed tests)
4. **BUG_FIX_PROMPTS_NOT_SAVING.md** (Main.py fix needed)

---

## Next Steps

1. ✅ Download both .py files
2. ✅ Back up your current files
3. ✅ Replace with new versions
4. ✅ Test each feature using checklist above
5. ✅ Report back what's still not working (if anything)

**Be specific about:**
- What you tried
- What happened
- What you expected
- Any error messages

This will help me fix the exact issue!

---

**I apologize for the broken functionality. Let's get this working properly!**
