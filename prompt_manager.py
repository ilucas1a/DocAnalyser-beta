"""
prompt_manager.py

Prompt Library management dialog for DocAnalyser.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

try:
    from context_help import add_help, HELP_TEXTS
    HELP_AVAILABLE = True
except ImportError:
    HELP_AVAILABLE = False
    def add_help(*args, **kwargs): pass
    HELP_TEXTS = {}


def open_prompt_manager_window(
    parent,
    prompts: list,
    prompts_path: str,
    save_func,
    refresh_callback,
    config: dict = None,
    save_config_func = None
):
    manager = tk.Toplevel(parent)
    manager.title("Prompts Library")
    manager.geometry("750x550")
    manager.configure(bg='#dcdad5')  # Match main window background
    
    current_editing_index = [None]
    displayed_prompts = [list(range(len(prompts)))]
    
    # ========== EXACT COPY OF DOCUMENTS LIBRARY PATTERN ==========
    
    # Header
    header_frame = ttk.Frame(manager, padding=10)
    header_frame.pack(fill=tk.X)
    ttk.Label(header_frame, text="Prompts Library", font=('Arial', 14, 'bold')).pack(side=tk.LEFT)

    # Search frame
    search_frame = ttk.Frame(manager, padding=10)
    search_frame.pack(fill=tk.X)
    
    ttk.Label(search_frame, text="Search:", font=('Arial', 10)).pack(side=tk.LEFT, padx=(0, 5))
    search_var = tk.StringVar()
    search_entry = tk.Entry(search_frame, textvariable=search_var, width=30, bg='#FFFDE6')
    search_entry.pack(side=tk.LEFT, padx=5)
    
    search_mode_var = tk.StringVar(value="Name")
    search_mode = ttk.Combobox(search_frame, textvariable=search_mode_var,
                               values=["Name", "Content", "Both"], state="readonly", width=10)
    search_mode.pack(side=tk.LEFT, padx=5)
    
    clear_search_btn = ttk.Button(search_frame, text="Clear", width=8,
               command=lambda: search_var.set(""))
    clear_search_btn.pack(side=tk.LEFT, padx=5)
    add_help(clear_search_btn, **HELP_TEXTS.get("prompts_library_clear_search", {}))
    
    results_label = ttk.Label(search_frame, text="")
    results_label.pack(side=tk.RIGHT, padx=10)

    # Main content frame
    content_frame = ttk.Frame(manager, padding=10)
    content_frame.pack(fill=tk.BOTH, expand=True)

    # List frame inside content
    list_frame = ttk.Frame(content_frame)
    list_frame.pack(fill=tk.X, pady=5)

    prompt_listbox = tk.Listbox(list_frame, height=6, selectmode=tk.EXTENDED, width=48, bg='#FFFDE6')
    prompt_listbox.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
    
    def populate_prompt_list(indices=None):
        prompt_listbox.delete(0, tk.END)
        if indices is None:
            indices = list(range(len(prompts)))
        displayed_prompts[0] = indices
        for idx in indices:
            if idx < len(prompts):
                prompt_listbox.insert(tk.END, prompts[idx]['name'])
    
    populate_prompt_list()

    name_frame = ttk.Frame(list_frame)
    name_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
    ttk.Label(name_frame, text="Prompt Name:").pack(anchor=tk.W)
    new_prompt_name = tk.StringVar(value=f"New Prompt {len(prompts) + 1}")
    tk.Entry(name_frame, textvariable=new_prompt_name, width=40, bg='#FFFDE6').pack(fill=tk.X, pady=5)

    # Text area
    ttk.Label(content_frame, text="Prompt Text:").pack(anchor=tk.W, pady=(5, 2))
    prompt_text_editor = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, height=6, bg='#FFFDE6')
    prompt_text_editor.pack(fill=tk.BOTH, expand=True)

    # Status
    prompt_status_var = tk.StringVar(value="Select a prompt to edit")
    ttk.Label(content_frame, textvariable=prompt_status_var, 
              font=('Arial', 9, 'italic'), foreground='blue').pack(anchor=tk.W, pady=(5, 0))

    # Button frame - at bottom (AFTER content_frame, matching Documents Library)
    button_frame = ttk.Frame(manager, padding=5)
    button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))

    # ========== HELPER FUNCTIONS ==========
    
    def update_editing_feedback(listbox_idx, prompt_name):
        for i in range(prompt_listbox.size()):
            prompt_listbox.itemconfig(i, bg='#FFFDE6', fg='black')
        if listbox_idx is not None and listbox_idx < prompt_listbox.size():
            prompt_listbox.itemconfig(listbox_idx, bg='lightgreen', fg='black')
        prompt_status_var.set(f"Editing: {prompt_name}")

    def perform_search(*args):
        query = search_var.get().strip().lower()
        mode = search_mode_var.get()
        current_editing_index[0] = None
        prompt_text_editor.delete('1.0', tk.END)
        new_prompt_name.set("")  # Clear the name field too
        prompt_status_var.set("Select a prompt to edit")
        
        # Clear any visual highlighting
        for i in range(prompt_listbox.size()):
            prompt_listbox.itemconfig(i, bg='#FFFDE6', fg='black')
        
        if not query:
            populate_prompt_list()
            results_label.config(text=f"{len(prompts)} prompts" if prompts else "")
            return
        
        matching = []
        for idx, p in enumerate(prompts):
            name, text = p.get('name', '').lower(), p.get('text', '').lower()
            if mode == "Name" and query in name: matching.append(idx)
            elif mode == "Content" and query in text: matching.append(idx)
            elif mode == "Both" and (query in name or query in text): matching.append(idx)
        
        if matching:
            populate_prompt_list(matching)
            results_label.config(text=f"{len(matching)} of {len(prompts)}")
        else:
            prompt_listbox.delete(0, tk.END)
            prompt_listbox.insert(tk.END, "No matches")
            displayed_prompts[0] = []
            results_label.config(text="0 results")
    
    search_var.trace_add('write', perform_search)
    search_mode_var.trace_add('write', perform_search)

    def on_select(event=None):
        sel = prompt_listbox.curselection()
        if sel and displayed_prompts[0] and sel[0] < len(displayed_prompts[0]):
            actual_idx = displayed_prompts[0][sel[0]]
            current_editing_index[0] = actual_idx
            prompt_text_editor.delete('1.0', tk.END)
            prompt_text_editor.insert('1.0', prompts[actual_idx]['text'])
            new_prompt_name.set(prompts[actual_idx]['name'])
            update_editing_feedback(sel[0], prompts[actual_idx]['name'])

    prompt_listbox.bind('<<ListboxSelect>>', on_select)
    if prompts:
        prompt_listbox.selection_set(0)
        on_select()

    def add_prompt():
        name = new_prompt_name.get().strip() or "New Prompt"
        if any(p['name'] == name for p in prompts):
            c = 1
            while any(p['name'] == f"New Prompt {c}" for p in prompts): c += 1
            name = f"New Prompt {c}"
        prompts.append({"name": name, "text": ""})
        search_var.set("")
        populate_prompt_list()
        prompt_text_editor.delete('1.0', tk.END)
        save_func(prompts_path, prompts)
        refresh_callback()
        prompt_listbox.selection_clear(0, tk.END)
        prompt_listbox.selection_set(len(prompts) - 1)
        prompt_listbox.see(len(prompts) - 1)
        current_editing_index[0] = len(prompts) - 1
        update_editing_feedback(len(prompts) - 1, name)

    def delete_prompt():
        sel = prompt_listbox.curselection()
        if sel and displayed_prompts[0] and sel[0] < len(displayed_prompts[0]):
            idx = displayed_prompts[0][sel[0]]
            if messagebox.askyesno("Confirm", f"Delete '{prompts[idx]['name']}'?"):
                prompts.pop(idx)
                prompt_text_editor.delete('1.0', tk.END)
                current_editing_index[0] = None
                save_func(prompts_path, prompts)
                refresh_callback()
                perform_search()

    def save_prompt():
        if current_editing_index[0] is None:
            messagebox.showerror("Error", "Select a prompt first")
            return
        idx = current_editing_index[0]
        if idx >= len(prompts):
            return
        new_name = new_prompt_name.get().strip()
        if not new_name:
            messagebox.showerror("Error", "Name cannot be empty")
            return
        if new_name != prompts[idx]['name'] and any(p['name'] == new_name for p in prompts):
            messagebox.showerror("Error", "Name already exists")
            return
        prompts[idx]['name'] = new_name
        prompts[idx]['text'] = prompt_text_editor.get('1.0', tk.END).strip()
        save_func(prompts_path, prompts)
        refresh_callback()
        perform_search()
        messagebox.showinfo("Success", "Saved!")

    def set_as_default():
        """Set the selected prompt as the default prompt on startup."""
        if current_editing_index[0] is None:
            messagebox.showerror("Error", "Select a prompt first")
            return
        idx = current_editing_index[0]
        if idx >= len(prompts):
            return
        prompt_name = prompts[idx]['name']
        
        if config is not None and save_config_func is not None:
            config['default_prompt'] = prompt_name
            save_config_func()
            messagebox.showinfo("Default Set", f"'{prompt_name}' is now the default prompt.\n\nIt will be pre-selected when you start DocAnalyser.")
        else:
            messagebox.showerror("Error", "Cannot save default - configuration not available")

    # ========== BUTTONS ==========
    ttk.Button(button_frame, text="Add New", command=add_prompt, width=12).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Save", command=save_prompt, width=12).pack(side=tk.LEFT, padx=5)
    ttk.Button(button_frame, text="Delete", command=delete_prompt, width=12).pack(side=tk.LEFT, padx=5)
    
    set_default_btn = ttk.Button(button_frame, text="Set as Default", command=set_as_default, width=14)
    set_default_btn.pack(side=tk.LEFT, padx=5)
    if HELP_AVAILABLE:
        add_help(set_default_btn, **HELP_TEXTS.get("set_default_prompt_button", {"title": "Set as Default", "description": "Make this prompt the default selection"}))
    
    ttk.Button(button_frame, text="Close", command=manager.destroy, width=12).pack(side=tk.RIGHT, padx=5)

    return manager
