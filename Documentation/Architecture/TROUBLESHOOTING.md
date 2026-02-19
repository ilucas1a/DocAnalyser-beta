# Troubleshooting Guide - Drag-Drop & Folder Creation

## Issue Report
1. ❌ Drag and drop not working
2. ❌ Can't create level 1 (root) folder

---

## Quick Tests

### Test 1: Drag and Drop
**Try this:**
1. Open Prompts Library
2. Select a prompt (click once)
3. Hold left mouse button DOWN
4. Drag at least 10 pixels in any direction
5. Hover over a folder (should see cursor change to hand or X)
6. Release mouse

**Expected:** Item moves to folder  
**If not working:** Check console for errors

### Test 2: Create Root Folder
**Try this:**
1. Open Prompts Library
2. Click in empty space to **deselect** everything
3. Click "⊕ New Folder" button
4. Enter name: "Test Root"
5. Click Create

**Expected:** New folder at root level  
**If not working:** What error do you see?

### Test 3: Create Subfolder
**Try this:**
1. Open Prompts Library
2. Click on "General" folder (or any folder)
3. Click "⊕ New Folder" button
4. Enter name: "Test Subfolder"
5. Dialog should say "Will be created in: General"
6. Click Create

**Expected:** New folder inside General  
**If not working:** What error?

---

## Common Issues & Fixes

### Issue A: Drag-Drop Does Nothing

**Possible Causes:**
1. Exception in drag handlers (check console)
2. Tree not accepting mouse events
3. Bindings not set up

**Debug Steps:**
1. Open Python console
2. Open Prompts Library
3. Try dragging
4. Look for error messages

**Quick Fix:**
Add debug output to on_drag_start:
```python
def on_drag_start(self, event):
    print(f"DEBUG: Drag start at ({event.x}, {event.y})")
    item_id = self.tree.identify_row(event.y)
    print(f"DEBUG: Item ID: {item_id}")
    if item_id:
        self.drag_data = {
            'item_id': item_id,
            'start_x': event.x,
            'start_y': event.y
        }
        print(f"DEBUG: Drag data set: {self.drag_data}")
```

If you see no "DEBUG:" messages, bindings aren't working.

### Issue B: Can't Create Root Folder When Item Selected

**Current Behavior:**
- If folder selected → Creates inside that folder
- If prompt selected → Creates at root
- If nothing selected → Creates at root

**To create at root when folder is selected:**
1. Click in empty space first (deselects)
2. Then click "⊕ New Folder"

**Better Solution (needs implementation):**
Add option in dialog to choose location:
```
┌─────────────────────────┐
│ Create New Folder       │
│                         │
│ Name: [My Folder     ]  │
│                         │
│ Location:               │
│ ◉ Root Level           │
│ ○ Inside: General      │
│                         │
│ [Create] [Cancel]       │
└─────────────────────────┘
```

---

## Diagnostic Commands

### Check if tree widget exists:
```python
print(hasattr(ui, 'tree'))
print(type(ui.tree))
```

### Check if drag handlers are bound:
```python
print(ui.tree.bind('<ButtonPress-1>'))
print(ui.tree.bind('<B1-Motion>'))
print(ui.tree.bind('<ButtonRelease-1>'))
```

### Check if buttons exist:
```python
print(hasattr(ui, 'btn_new_folder'))
print(hasattr(ui, 'btn_move_up'))
print(hasattr(ui, 'btn_move_down'))
```

---

## What Should Be Working

### Buttons That Should Exist:
- [x] ⊕ New Folder
- [x] ⊕ New Prompt
- [x] ✏️ Rename
- [x] 🗑️ Delete
- [x] ↑ Move Up
- [x] ↓ Move Down

### Keyboard Shortcuts That Should Work:
- [x] F2 - Rename
- [x] Delete - Delete
- [x] Ctrl+X - Cut
- [x] Ctrl+V - Paste
- [x] Ctrl+Up - Move up
- [x] Ctrl+Down - Move down

### Drag-Drop That Should Work:
- [x] Drag prompt into folder
- [x] Drag folder into folder
- [x] Visual cursor feedback (hand or X)
- [x] Drop validation

---

## Files That Need To Be Correct

1. **tree_manager_base.py** (1290 lines)
   - Has drag-drop handlers
   - Has create_new_folder
   - Has move_up/down methods

2. **prompt_tree_manager.py** (980+ lines)
   - Overrides create_ui
   - Calls setup_drag_drop()
   - Calls setup_keyboard_shortcuts()
   - Has Move Up/Down buttons

---

## Quick Verification Script

Run this in Python console after opening library:

```python
# Get the UI instance (you'll need to store it)
# ui = ... (however you access it)

# Check buttons
print("Buttons:")
print(f"  New Folder: {hasattr(ui, 'btn_new_folder')}")
print(f"  Move Up: {hasattr(ui, 'btn_move_up')}")
print(f"  Move Down: {hasattr(ui, 'btn_move_down')}")

# Check tree
print(f"\nTree widget: {hasattr(ui, 'tree')}")

# Check drag state
print(f"Drag data: {ui.drag_data}")

# Try to drag
print("\nNow try dragging an item and watch for output")
```

---

## Expected Console Output

**When opening library:**
```
DEBUG: Loading from file: C:\...\prompts.json
DEBUG: Loading tree format version 2.0
```

**When dragging:**
```
DEBUG: Drag start at (150, 200)
DEBUG: Item ID: I001
DEBUG: Drag data set: {'item_id': 'I001', ...}
DEBUG: Drag motion - delta: 25px
DEBUG: Target: General (folder)
DEBUG: Can drop: True
```

**When creating folder:**
```
DEBUG: Create folder clicked
DEBUG: Selection: None
DEBUG: Will create at root
DEBUG: Created folder: Test Root
```

---

## If Nothing Works

### Nuclear Option - Reinstall:

1. **Backup current files**
2. **Delete:**
   - tree_manager_base.py
   - prompt_tree_manager.py
3. **Copy fresh versions from earlier in conversation**
4. **Test basic functionality first**

---

## Report Back

Please try:

1. **Test 1** (drag-drop) - What happens?
2. **Test 2** (root folder) - What happens?
3. **Test 3** (subfolder) - What happens?

And tell me:
- Do you see the Move Up/Down buttons?
- What error messages appear?
- Does console show any DEBUG output?

This will help me understand exactly what's broken!
