# CRITICAL BUG FIX - Prompts Not Saving

**Issue:** Changes to prompts library not persisting between opens.

**Root Cause:** Main.py is using stale in-memory prompts list instead of reloading from file.

---

## The Problem

### Current Flow (BROKEN):
```
1. Open Prompts Library
   → Loads from Main.py's in-memory list (stale!)
   
2. Edit prompt, click "Save All Changes"
   → Saves to prompts.json ✓
   → Calls refresh_callback()
   → Main.py refreshes dropdown from in-memory list ✗
   
3. Close library, reopen
   → Loads from stale in-memory list again ✗
   → Changes lost!
```

### Root Issue:
**Main.py never reloads prompts from file after save!**

---

## The Fix

### Required Changes to Main.py

**Find the refresh function (around line 2000-2100):**

**BEFORE (Broken):**
```python
def refresh_prompts_list():
    """Refresh prompts dropdown"""
    global prompts, prompt_var
    
    # Just update dropdown from in-memory list
    prompt_names = [p['name'] for p in prompts]
    prompt_dropdown['values'] = prompt_names
    
    if prompt_var.get() not in prompt_names:
        prompt_var.set(prompt_names[0] if prompt_names else "")
```

**AFTER (Fixed):**
```python
def refresh_prompts_list():
    """Refresh prompts dropdown - RELOAD FROM FILE"""
    global prompts, prompt_var
    
    # CRITICAL: Reload from file to get latest changes
    prompts = load_prompts_from_file(prompts_path)
    
    # Update dropdown
    prompt_names = [p['name'] for p in prompts]
    prompt_dropdown['values'] = prompt_names
    
    if prompt_var.get() not in prompt_names:
        prompt_var.set(prompt_names[0] if prompt_names else "")
    
    print(f"DEBUG: Reloaded {len(prompts)} prompts from file")
```

---

## Step-by-Step Fix

### Step 1: Locate refresh_prompts_list() function

Search for:
```python
def refresh_prompts_list():
```

Or similar function that refreshes the prompt dropdown.

### Step 2: Add reload from file

Add this line at the START of the function:
```python
prompts = load_prompts_from_file(prompts_path)
```

### Step 3: Import if needed

Make sure `load_prompts_from_file` is imported:
```python
from prompt_tree_manager import load_prompts_from_file
```

### Step 4: Test

1. Open Prompts Library
2. Add/edit a prompt
3. Click "Save All Changes"
4. Close library
5. Reopen library
6. **Verify changes are there!** ✓

---

## Alternative Fix (If refresh function is complex)

If you can't easily modify the refresh function, fix it in the button handler:

**Find the "Prompts Library" button code:**

```python
def open_prompts_library_btn():
    # CRITICAL: Reload from file BEFORE opening
    global prompts
    prompts = load_prompts_from_file(prompts_path)
    
    open_prompt_tree_manager(
        parent=root,
        prompts=prompts,
        prompts_path=prompts_path,
        save_func=save_json,
        refresh_callback=refresh_prompts_list,
        config=config,
        save_config_func=save_config
    )
```

This ensures you ALWAYS load fresh data before opening the library.

---

## Updated prompt_tree_manager.py

I've already fixed `prompt_tree_manager.py` to:

1. ✅ **Always load from file first** (line ~871-956)
2. ✅ Ignore stale in-memory list
3. ✅ Handle migration from old format
4. ✅ Fall back gracefully if file doesn't exist

**New behavior:**
```python
def open_prompt_tree_manager(...):
    # ALWAYS load from file first!
    if os.path.exists(prompts_path):
        with open(prompts_path, 'r') as f:
            data = json.load(f)
        tree = TreeManager.from_dict(data, ...)
    else:
        # Only use in-memory list if file doesn't exist
        tree = create_from_list(prompts)
```

---

## Testing Checklist

### Test 1: Create New Prompt
- [ ] Open library
- [ ] Click "New Prompt"
- [ ] Enter name: "Test Persistence"
- [ ] Enter text: "This is a test"
- [ ] Click Save All Changes
- [ ] Close library
- [ ] **Reopen library**
- [ ] **Verify "Test Persistence" is there** ✓

### Test 2: Edit Existing Prompt
- [ ] Open library
- [ ] Select existing prompt
- [ ] Edit text
- [ ] Click Save All Changes
- [ ] Close library
- [ ] **Reopen library**
- [ ] **Verify changes saved** ✓

### Test 3: Delete Prompt
- [ ] Open library
- [ ] Delete a prompt
- [ ] Click Save All Changes
- [ ] Close library
- [ ] **Reopen library**
- [ ] **Verify prompt is gone** ✓

### Test 4: Create Folder
- [ ] Open library
- [ ] Create new folder
- [ ] Add prompts to folder
- [ ] Click Save All Changes
- [ ] Close library
- [ ] **Reopen library**
- [ ] **Verify folder structure intact** ✓

### Test 5: Rename Items
- [ ] Open library
- [ ] Rename folder or prompt
- [ ] Click Save All Changes
- [ ] Close library
- [ ] **Reopen library**
- [ ] **Verify new name persists** ✓

---

## Debug Output

If changes still don't persist, add debug output:

```python
def open_prompts_library_btn():
    global prompts
    
    print(f"DEBUG: Before reload - {len(prompts)} prompts in memory")
    print(f"DEBUG: Loading from: {prompts_path}")
    
    prompts = load_prompts_from_file(prompts_path)
    
    print(f"DEBUG: After reload - {len(prompts)} prompts loaded")
    print(f"DEBUG: Prompts: {[p['name'] for p in prompts]}")
    
    open_prompt_tree_manager(...)
```

Check console output when you reopen the library.

---

## File Verification

**Check if prompts.json is actually being written:**

```python
def save_tree(self):
    tree_dict = self.tree_manager.to_dict()
    
    print(f"DEBUG: Saving to {self.prompts_path}")
    print(f"DEBUG: Data: {json.dumps(tree_dict, indent=2)[:500]}...")
    
    self.save_func_external(self.prompts_path, tree_dict)
    
    # Verify file was written
    if os.path.exists(self.prompts_path):
        size = os.path.getsize(self.prompts_path)
        print(f"DEBUG: File written successfully, size: {size} bytes")
    else:
        print(f"ERROR: File was NOT written!")
```

---

## Common Issues

### Issue 1: File path wrong
**Symptom:** File saves but loads empty list  
**Fix:** Verify `prompts_path` is correct absolute path

### Issue 2: Permissions error
**Symptom:** "Permission denied" when saving  
**Fix:** Check file permissions, run as admin if needed

### Issue 3: JSON corruption
**Symptom:** Error loading file after save  
**Fix:** Check prompts.json for syntax errors

### Issue 4: save_json function broken
**Symptom:** No error but file not updated  
**Fix:** Check save_json function writes correctly:
```python
def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

---

## Summary

**The core fix is simple:**

**ALWAYS reload from file before opening library:**
```python
prompts = load_prompts_from_file(prompts_path)
```

**And/or reload after saving:**
```python
def refresh_prompts_list():
    global prompts
    prompts = load_prompts_from_file(prompts_path)  # ← Add this!
    # ... rest of function
```

This ensures you NEVER use stale data!

---

## Quick Fix Version

**Minimum change needed in Main.py:**

Find this line (where Prompts Library button is):
```python
open_prompt_tree_manager(parent, prompts, ...)
```

Change to:
```python
# Reload from file BEFORE opening
prompts = load_prompts_from_file(prompts_path)
open_prompt_tree_manager(parent, prompts, ...)
```

**That's it!** This single line ensures fresh data.

---

## Files Updated

1. ✅ **prompt_tree_manager.py** - Fixed to always load from file
2. ⚠️ **Main.py** - Needs fix to reload on refresh/open

---

**After applying fix, test immediately with the checklist above!**
