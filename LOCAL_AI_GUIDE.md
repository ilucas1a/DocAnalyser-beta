# Running AI Locally with Ollama

## A Beginner's Guide for DocAnalyser Users

This guide explains how to run AI models on your own computer instead of using cloud services. This keeps your documents completely private and costs nothing after setup.

---

## Why Run AI Locally?

**Privacy**: Your documents never leave your computer. No data is sent to OpenAI, Google, or any other company.

**Cost**: After the initial setup, local AI is completely free. No API keys, no usage fees, no subscriptions.

**Offline Use**: Works without an internet connection once set up.

**Trade-offs**: Local AI is generally slower than cloud services, and may produce slightly less sophisticated results for complex tasks. However, for routine summarisation and simple Q&A, the difference is often negligible.

---

## What You'll Need

### Minimum Requirements
- **RAM**: 8 GB (for tiny models) or 16 GB (recommended)
- **Storage**: 5-20 GB free space (models are large files)
- **Operating System**: Windows 10/11, macOS, or Linux

### Recommended for Better Performance
- **RAM**: 32 GB (allows larger, more capable models)
- **GPU**: NVIDIA, AMD, or Intel Arc graphics card (optional but significantly faster)
- **Apple Silicon**: M1/M2/M3 Macs work excellently with local AI

### How to Check Your RAM (Windows)
1. Press `Ctrl + Shift + Esc` to open Task Manager
2. Click the "Performance" tab
3. Look at "Memory" - this shows your total RAM

---

## Quick Start (5 Steps)

### Step 1: Install Ollama

1. Go to **https://ollama.com** in your web browser
2. Click **Download** for your operating system
3. Run the installer (Windows) or drag to Applications (Mac)
4. Ollama starts automatically in the background — no window to manage!

*That's it for installation. Ollama runs quietly in the background.*

---

### Step 2: Check the Connection

1. Open DocAnalyser
2. Click **Settings ▾** (top right of the main window)
3. Click **Local AI Setup**
4. The wizard will check whether Ollama is installed and connected
5. Click **Test Connection** if needed

If you see "✅ Connected", you're ready for the next step.

**Troubleshooting**: If "Not connected", look for the Ollama icon in your system tray (bottom right of taskbar on Windows). If it's not there, search for "Ollama" in the Start menu and launch it.

---

### Step 3: Download a Model

The Local AI Setup wizard shows recommended models based on your computer's hardware (RAM, GPU). To download one:

1. Open a command prompt: press `Win+R`, type `cmd`, press Enter
2. Type one of the commands below and press Enter
3. Wait for the download to finish

**Recommended starting model**: `ollama pull llama3.2:3b` (2 GB download, works on most computers)

The wizard provides copy-paste commands tailored to your system — just click "Copy" and paste into the terminal.

---

### Step 4: Select the Model in DocAnalyser

1. Click **Settings ▾** → **AI Settings**
2. Set **AI Provider** to **"Ollama (Local)"**
3. Click **Refresh Models** — your downloaded model will appear
4. Select your model from the **AI Model** dropdown

---

### Step 5: Start Analysing

1. Load a document (drag a file, paste a URL, or click Browse)
2. Select a prompt from the Prompts Library or type your own
3. Click **Run**

The status bar will show that local AI is processing your request.

---

## What DocAnalyser Does Automatically

Once you've installed Ollama and downloaded a model, DocAnalyser handles everything else:

| Feature | What DocAnalyser Does For You |
|---------|------------------------------|
| **Model Detection** | Automatically finds all your installed Ollama models |
| **Model Loading** | Models load automatically when needed |
| **Chunk Size** | Automatically adjusts based on your model's context window |
| **System Detection** | Identifies your RAM, GPU, and recommends compatible models |
| **Connection** | Connects to Ollama automatically on localhost |

---

## Recommended Models by Computer Specs

| Your RAM | Recommended Model | Download Command | Size | Quality |
|----------|------------------|-----------------|------|---------|
| 8 GB | Llama 3.2 1B | `ollama pull llama3.2:1b` | 1.3 GB | ⭐⭐ Basic |
| 16 GB | **Llama 3.2 3B** | `ollama pull llama3.2:3b` | 2.0 GB | ⭐⭐⭐ Good |
| 16 GB | Phi-3 Mini | `ollama pull phi3:mini` | 2.3 GB | ⭐⭐⭐ Good |
| 24 GB | Mistral 7B | `ollama pull mistral:7b` | 4.1 GB | ⭐⭐⭐⭐ Very Good |
| 32 GB | **Llama 3.1 8B** | `ollama pull llama3.1:8b` | 4.7 GB | ⭐⭐⭐⭐⭐ Excellent |
| 32 GB | Qwen 2.5 7B | `ollama pull qwen2:7b` | 4.4 GB | ⭐⭐⭐⭐⭐ Excellent |
| 48 GB+ | Qwen 2.5 14B | `ollama pull qwen2:14b` | 9.0 GB | ⭐⭐⭐⭐⭐ Excellent |

**Best choices for most users**:
- **Budget/older PC**: Llama 3.2 3B — fast and capable
- **Modern PC (32GB)**: Llama 3.1 8B — excellent quality, good speed
- **Reasoning tasks**: DeepSeek R1 7B (`ollama pull deepseek-r1:7b`) — specialised for analysis

You can install multiple models. They only use RAM when actively running.

---

## Using DocAnalyser's Built-in Tools

DocAnalyser provides several tools to help with local AI setup. All are accessible from the **Settings ▾** menu:

| Tool | Where to Find It | What It Does |
|------|------------------|--------------|
| **Local AI Setup** | Settings ▾ → Local AI Setup | Step-by-step wizard with hardware detection and model recommendations |
| **AI Settings** | Settings ▾ → AI Settings | Select provider, model, test connection, manage models |
| **System Check** | AI Settings → System Check button | Detailed hardware analysis with model compatibility |
| **Local AI Guide** | AI Settings → Local AI Guide button | This guide (opens in a window) |
| **Manage Models** | AI Settings → Manage Models button | View, download, and delete Ollama models |

---

## Quick Reference: Cloud vs Local

| Aspect | Cloud API | Local (Ollama) |
|--------|-----------|----------------|
| **Privacy** | Data sent to provider | 🔒 Completely private |
| **Cost** | Pay per use | 🆓 Free after setup |
| **Speed** | ⚡ Fast (5-15 sec) | Slower (15-60 sec) |
| **Quality** | ⭐⭐⭐⭐⭐ Excellent | ⭐⭐⭐–⭐⭐⭐⭐⭐ Good to Excellent |
| **Internet** | Required | Not required |
| **Setup** | Just need API key | Install Ollama + download model |

---

## Recommended Workflow

For users who want privacy but also need speed occasionally:

1. **Daily summarisation tasks** → Use Ollama with Llama 3.2 3B (fast, private)
2. **Complex analysis** → Use Ollama with Llama 3.1 8B or DeepSeek R1
3. **Time-critical work** → Switch to a cloud provider temporarily
4. **Sensitive/confidential documents** → Always use local

DocAnalyser makes it easy to switch between providers — just change the dropdown.

---

## Troubleshooting

### "Ollama is not installed"
- Download Ollama from https://ollama.com
- Run the installer
- Restart DocAnalyser

### "Not connected — is Ollama running?"
- **Windows**: Look for the Ollama icon in the system tray (bottom right). If not there, search for "Ollama" in the Start menu and run it.
- **Mac**: Look for Ollama in the menu bar. If not there, open Ollama from Applications.
- **Linux**: Run `ollama serve` in a terminal.

### "No models installed"
- Open a terminal and run: `ollama pull llama3.2:3b`
- Or use Settings ▾ → Local AI Setup for guided instructions

### Models Not Appearing in Dropdown
- Click **Refresh Models** in AI Settings
- Make sure Ollama is running (check system tray)
- Try restarting DocAnalyser

### Very Slow Generation
- Try a smaller model (3B instead of 8B)
- Close other applications to free up RAM
- Check if your GPU is being used (NVIDIA/AMD users)

### Poor Quality Results
- Try a larger model if your RAM allows
- Use more specific prompts
- For complex analysis, consider Llama 3.1 8B or DeepSeek R1

### Out of Memory Errors
- Your model may be too large for your RAM
- Download a smaller model (e.g., Llama 3.2 3B instead of 8B)
- Close other applications

---

## Command Line Reference (Optional)

If you prefer using the terminal, Ollama has simple commands:

```
ollama pull llama3.2:3b     # Download a model
ollama list                  # See installed models
ollama rm llama3.2:3b       # Delete a model
ollama run llama3.2:3b      # Test a model interactively (type /bye to exit)
```

---

## Getting Help

- **Ollama Documentation**: https://ollama.com/library
- **Ollama GitHub**: https://github.com/ollama/ollama
- **DocAnalyser**: Right-click any button for context-sensitive help

---

## Summary: Your Setup Checklist

- [ ] Download and install Ollama from https://ollama.com
- [ ] Open DocAnalyser → Settings ▾ → Local AI Setup
- [ ] Check your system profile and recommended models
- [ ] Download a model: `ollama pull llama3.2:3b` (or as recommended)
- [ ] In AI Settings: set provider to "Ollama (Local)" and click Refresh Models
- [ ] Select your model and run a prompt!

**That's it!** DocAnalyser handles chunk sizes, model loading, and connections automatically.

---

*Guide version 3.0 — February 2026*
*For DocAnalyser v1.4.0 (Beta)*
