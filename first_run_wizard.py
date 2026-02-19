"""
first_run_wizard.py - First Run Setup Wizard for DocAnalyser

Shows on first launch to help users configure the app,
with a focus on Local AI setup for privacy-conscious users.
"""

import tkinter as tk
from tkinter import ttk
import webbrowser
import os
import json


# LM Studio download URL
LM_STUDIO_URL = "https://lmstudio.ai/"


def get_config_dir():
    """Get the user's config directory"""
    if os.name == 'nt':  # Windows
        base = os.environ.get('APPDATA', os.path.expanduser('~'))
        return os.path.join(base, 'DocAnalyser_Beta')
    else:  # macOS/Linux
        return os.path.join(os.path.expanduser('~'), '.docanalyser_beta')


def has_run_before():
    """Check if the first-run wizard has been completed"""
    config_dir = get_config_dir()
    wizard_flag = os.path.join(config_dir, '.first_run_complete')
    return os.path.exists(wizard_flag)


def mark_wizard_complete():
    """Mark the first-run wizard as completed"""
    config_dir = get_config_dir()
    os.makedirs(config_dir, exist_ok=True)
    wizard_flag = os.path.join(config_dir, '.first_run_complete')
    with open(wizard_flag, 'w') as f:
        f.write('1')


def check_lm_studio_running():
    """Check if LM Studio's local server is accessible"""
    try:
        import urllib.request
        req = urllib.request.Request('http://localhost:1234/v1/models', method='GET')
        req.add_header('Content-Type', 'application/json')
        with urllib.request.urlopen(req, timeout=2) as response:
            return response.status == 200
    except:
        return False


def show_first_run_wizard(parent, on_complete_callback=None, show_local_ai_guide_callback=None):
    """
    Show the first-run wizard dialog.
    
    Args:
        parent: Parent Tk window
        on_complete_callback: Function to call when wizard completes
        show_local_ai_guide_callback: Function to show the Local AI Guide
    """
    
    wizard = tk.Toplevel(parent)
    wizard.title("Welcome to DocAnalyser")
    wizard.geometry("600x600")
    wizard.transient(parent)
    wizard.grab_set()
    
    # Prevent closing without completing
    wizard.protocol("WM_DELETE_WINDOW", lambda: None)
    
    # Center on screen
    wizard.update_idletasks()
    x = (wizard.winfo_screenwidth() - 600) // 2
    y = (wizard.winfo_screenheight() - 580) // 2
    wizard.geometry(f"+{x}+{y}")
    
    # Track current page
    current_page = [0]
    
    # Main container
    main_frame = tk.Frame(wizard, bg='#f0f0f0')
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    # Content area (changes per page)
    content_frame = tk.Frame(main_frame, bg='#f0f0f0')
    content_frame.pack(fill=tk.BOTH, expand=True, padx=30, pady=20)
    
    # Navigation buttons at bottom
    nav_frame = tk.Frame(main_frame, bg='#e0e0e0', height=60)
    nav_frame.pack(fill=tk.X, side=tk.BOTTOM)
    nav_frame.pack_propagate(False)
    
    back_btn = ttk.Button(nav_frame, text="← Back", width=12)
    back_btn.pack(side=tk.LEFT, padx=20, pady=15)
    
    next_btn = ttk.Button(nav_frame, text="Next →", width=12)
    next_btn.pack(side=tk.RIGHT, padx=20, pady=15)
    
    skip_btn = ttk.Button(nav_frame, text="Skip Setup", width=12)
    skip_btn.pack(side=tk.RIGHT, padx=5, pady=15)
    
    def clear_content():
        for widget in content_frame.winfo_children():
            widget.destroy()
    
    def show_page(page_num):
        current_page[0] = page_num
        clear_content()
        
        if page_num == 0:
            show_welcome_page()
        elif page_num == 1:
            show_ai_choice_page()
        elif page_num == 2:
            show_local_ai_page()
        elif page_num == 3:
            show_complete_page()
        
        # Update button states
        back_btn.config(state=tk.NORMAL if page_num > 0 else tk.DISABLED)
        
        if page_num == 3:  # Final page
            next_btn.config(text="Get Started!", command=finish_wizard)
            skip_btn.pack_forget()
        else:
            next_btn.config(text="Next →", command=lambda: show_page(current_page[0] + 1))
            if not skip_btn.winfo_ismapped():
                skip_btn.pack(side=tk.RIGHT, padx=5, pady=15)
    
    def show_welcome_page():
        """Page 0: Welcome"""
        tk.Label(
            content_frame,
            text="👋 Welcome to DocAnalyser!",
            font=('Arial', 20, 'bold'),
            bg='#f0f0f0',
            fg='#000080'
        ).pack(pady=(20, 10))
        
        tk.Label(
            content_frame,
            text="Universal Document Analysis Tool",
            font=('Arial', 12),
            bg='#f0f0f0',
            fg='#444444'
        ).pack(pady=(0, 30))
        
        welcome_text = """DocAnalyser helps you extract and analyse text from:

    📄  Documents (PDF, Word, text files)
    🎬  YouTube videos (transcripts)
    🎤  Audio and video files
    🌐  Web pages

You can then use AI to summarise, analyse, and extract
insights from your documents.

This quick setup will help you get started."""
        
        tk.Label(
            content_frame,
            text=welcome_text,
            font=('Arial', 11),
            bg='#f0f0f0',
            fg='#333333',
            justify=tk.LEFT
        ).pack(pady=10, anchor=tk.W)
    
    # Variable to track AI preference
    ai_preference = tk.StringVar(value="cloud")
    
    def show_ai_choice_page():
        """Page 1: Choose AI approach"""
        tk.Label(
            content_frame,
            text="🤖 How would you like to use AI?",
            font=('Arial', 16, 'bold'),
            bg='#f0f0f0',
            fg='#000080'
        ).pack(pady=(10, 20))
        
        # Option 1: Cloud AI
        cloud_frame = tk.Frame(content_frame, bg='#ffffff', bd=1, relief='solid')
        cloud_frame.pack(fill=tk.X, pady=10, ipady=10, ipadx=10)
        
        tk.Radiobutton(
            cloud_frame,
            text="☁️  Cloud AI (OpenAI, Claude, Gemini, etc.)",
            variable=ai_preference,
            value="cloud",
            font=('Arial', 11, 'bold'),
            bg='#ffffff',
            fg='#000080',
            anchor=tk.W
        ).pack(anchor=tk.W, padx=10, pady=(10, 0))
        
        tk.Label(
            cloud_frame,
            text="• Requires API keys (some have free tiers)\n• Most powerful models available\n• Documents are sent to cloud servers",
            font=('Arial', 10),
            bg='#ffffff',
            fg='#555555',
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=30, pady=(0, 10))
        
        # Option 2: Local AI
        local_frame = tk.Frame(content_frame, bg='#ffffff', bd=1, relief='solid')
        local_frame.pack(fill=tk.X, pady=10, ipady=10, ipadx=10)
        
        tk.Radiobutton(
            local_frame,
            text="🏠  Local AI (LM Studio - runs on your computer)",
            variable=ai_preference,
            value="local",
            font=('Arial', 11, 'bold'),
            bg='#ffffff',
            fg='#000080',
            anchor=tk.W
        ).pack(anchor=tk.W, padx=10, pady=(10, 0))
        
        tk.Label(
            local_frame,
            text="• Completely free - no API costs\n• 100% private - documents never leave your computer\n• Requires 16GB+ RAM (32GB recommended)\n• Requires downloading LM Studio",
            font=('Arial', 10),
            bg='#ffffff',
            fg='#555555',
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=30, pady=(0, 10))
        
        # Option 3: Both
        both_frame = tk.Frame(content_frame, bg='#ffffff', bd=1, relief='solid')
        both_frame.pack(fill=tk.X, pady=10, ipady=10, ipadx=10)
        
        tk.Radiobutton(
            both_frame,
            text="🔄  Both (use local for privacy, cloud for power)",
            variable=ai_preference,
            value="both",
            font=('Arial', 11, 'bold'),
            bg='#ffffff',
            fg='#000080',
            anchor=tk.W
        ).pack(anchor=tk.W, padx=10, pady=(10, 0))
        
        tk.Label(
            both_frame,
            text="• Best of both worlds\n• Switch between providers as needed",
            font=('Arial', 10),
            bg='#ffffff',
            fg='#555555',
            justify=tk.LEFT
        ).pack(anchor=tk.W, padx=30, pady=(0, 10))
        
        # Update next button based on choice
        def update_next():
            choice = ai_preference.get()
            if choice in ("local", "both"):
                next_btn.config(command=lambda: show_page(2))  # Go to Local AI setup
            else:
                next_btn.config(command=lambda: show_page(3))  # Skip to complete
        
        ai_preference.trace_add('write', lambda *args: update_next())
        update_next()
    
    def show_local_ai_page():
        """Page 2: Local AI Setup"""
        tk.Label(
            content_frame,
            text="🏠 Setting Up Local AI",
            font=('Arial', 16, 'bold'),
            bg='#f0f0f0',
            fg='#000080'
        ).pack(pady=(10, 20))
        
        # Check if LM Studio is already running
        lm_running = check_lm_studio_running()
        
        if lm_running:
            # Already set up!
            tk.Label(
                content_frame,
                text="✅ LM Studio detected and running!",
                font=('Arial', 12, 'bold'),
                bg='#f0f0f0',
                fg='#228B22'
            ).pack(pady=10)
            
            tk.Label(
                content_frame,
                text="Great news! LM Studio is already running on your computer.\nYou're all set to use Local AI with DocAnalyser.",
                font=('Arial', 11),
                bg='#f0f0f0',
                fg='#333333',
                justify=tk.CENTER
            ).pack(pady=10)
        else:
            # Need to set up
            tk.Label(
                content_frame,
                text="To use Local AI, you'll need to install LM Studio:",
                font=('Arial', 11),
                bg='#f0f0f0',
                fg='#333333'
            ).pack(pady=(0, 15), anchor=tk.W)
            
            # Steps
            steps_frame = tk.Frame(content_frame, bg='#f0f0f0')
            steps_frame.pack(fill=tk.X, pady=10)
            
            steps = [
                ("1️⃣", "Download LM Studio (free)", "Click the button below to open the download page"),
                ("2️⃣", "Install and open LM Studio", "Run the installer, then launch the app"),
                ("3️⃣", "Download an AI model", "In LM Studio, search for and download a model\n(Recommended: Llama 3.2 or Qwen 2.5)"),
                ("4️⃣", "Start the local server", "In LM Studio, go to 'Local Server' tab and click Start"),
            ]
            
            for icon, title, desc in steps:
                step_frame = tk.Frame(steps_frame, bg='#f0f0f0')
                step_frame.pack(fill=tk.X, pady=5)
                
                tk.Label(
                    step_frame,
                    text=icon,
                    font=('Arial', 14),
                    bg='#f0f0f0'
                ).pack(side=tk.LEFT, padx=(0, 10))
                
                text_frame = tk.Frame(step_frame, bg='#f0f0f0')
                text_frame.pack(side=tk.LEFT, fill=tk.X)
                
                tk.Label(
                    text_frame,
                    text=title,
                    font=('Arial', 10, 'bold'),
                    bg='#f0f0f0',
                    fg='#000080',
                    anchor=tk.W
                ).pack(anchor=tk.W)
                
                tk.Label(
                    text_frame,
                    text=desc,
                    font=('Arial', 9),
                    bg='#f0f0f0',
                    fg='#555555',
                    anchor=tk.W
                ).pack(anchor=tk.W)
            
            # Buttons
            btn_frame = tk.Frame(content_frame, bg='#f0f0f0')
            btn_frame.pack(pady=20)
            
            def open_lm_studio_download():
                webbrowser.open(LM_STUDIO_URL)
            
            download_btn = ttk.Button(
                btn_frame,
                text="🌐 Download LM Studio",
                command=open_lm_studio_download,
                width=25
            )
            download_btn.pack(pady=5)
            
            if show_local_ai_guide_callback:
                guide_btn = ttk.Button(
                    btn_frame,
                    text="📖 View Detailed Guide",
                    command=lambda: show_local_ai_guide_callback(),
                    width=25
                )
                guide_btn.pack(pady=5)
            
            tk.Label(
                content_frame,
                text="💡 You can set this up later from Settings → Local AI Guide",
                font=('Arial', 9, 'italic'),
                bg='#f0f0f0',
                fg='#666666'
            ).pack(pady=(10, 0))
    
    def show_complete_page():
        """Page 3: Setup Complete"""
        tk.Label(
            content_frame,
            text="🎉 You're All Set!",
            font=('Arial', 20, 'bold'),
            bg='#f0f0f0',
            fg='#000080'
        ).pack(pady=(30, 20))
        
        tk.Label(
            content_frame,
            text="DocAnalyser is ready to use.",
            font=('Arial', 12),
            bg='#f0f0f0',
            fg='#333333'
        ).pack(pady=(0, 30))
        
        tips_text = """Quick Tips:

    💡  Right-click buttons and text areas for help where it is needed
    
    💡  Click the red ❓ button for a quick intro
    
    💡  Use Settings (lower right corner) to add your API keys for cloud AI providers
    
    💡  Drag and drop files directly into the app"""
        
        tk.Label(
            content_frame,
            text=tips_text,
            font=('Arial', 11),
            bg='#f0f0f0',
            fg='#333333',
            justify=tk.LEFT
        ).pack(pady=10, anchor=tk.W)
    
    def finish_wizard():
        """Complete the wizard and close"""
        mark_wizard_complete()
        wizard.destroy()
        if on_complete_callback:
            on_complete_callback()
    
    def skip_wizard():
        """Skip the wizard"""
        mark_wizard_complete()
        wizard.destroy()
        if on_complete_callback:
            on_complete_callback()
    
    # Configure buttons
    back_btn.config(command=lambda: show_page(current_page[0] - 1))
    skip_btn.config(command=skip_wizard)
    
    # Show first page
    show_page(0)
    
    return wizard


def reset_wizard():
    """Reset the wizard so it shows again on next launch (for testing)"""
    config_dir = get_config_dir()
    wizard_flag = os.path.join(config_dir, '.first_run_complete')
    if os.path.exists(wizard_flag):
        os.remove(wizard_flag)
        print("First-run wizard reset. It will show on next launch.")
    else:
        print("First-run wizard flag not found.")


# Demo/test
if __name__ == "__main__":
    root = tk.Tk()
    root.title("DocAnalyser")
    root.geometry("800x600")
    
    # For testing, reset the wizard
    reset_wizard()
    
    def on_complete():
        print("Wizard completed!")
        tk.Label(root, text="Main app would load here", font=('Arial', 14)).pack(expand=True)
    
    def show_guide():
        print("Would show Local AI Guide")
    
    # Show wizard if first run
    if not has_run_before():
        root.after(100, lambda: show_first_run_wizard(root, on_complete, show_guide))
    else:
        on_complete()
    
    root.mainloop()
