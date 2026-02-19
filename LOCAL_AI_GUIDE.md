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

## Quick Start (3 Steps)

### Step 1: Install Ollama

1. Go to **https://ollama.com** in your web browser
2. Click **Download** for your operating system
3. Run the installer (Windows) or drag to Applications (Mac)
4. Ollama starts automatically in the background - no window to manage!

*That's it for installation. Ollama runs quietly in the background.*

---

### Step 2: Use DocAnalyser's Setup Wizard

DocAnalyser includes a built-in wizard that makes setup easy:

1. Open DocAnalyser
2. Click **Settings** (top right)
3. Click the **🤖 Local AI Setup** button
4. The wizard will show you:
   - ✅ Whether Ollama is installed and running
   - 📊 Your computer's capabilities (RAM, GPU)
   - 📦 Compatible models for your hardware

---

### Step 3: Download a Model

In the Local AI Setup wizard:

1. Browse the list of available models
2. Models are sorted by compatibility with your hardware
3. Click to select a model (green ✅ = already installed)
4. Click **Download Selected**
5. Wait for the download to complete

**Recommended first model**: **Llama 3.2 3B** (2 GB download, works on most computers)

---

## What DocAnalyser Does Automatically

Once you've installed Ollama and downloaded a model, DocAnalyser handles everything else:

| Feature | What DocAnalyser Does For You |
|---------|------------------------------|
| **Model Detection** | Automatically finds all your installed Ollama models |
| **Model Loading** | Models load automatically when needed (no manual loading required) |
| **Chunk Size** | Automatically adjusts based on your model's context window |
| **System Detection** | Identifies your RAM, GPU, and recommends compatible models |
| **Connection** | Connects to Ollama automatically on localhost |

### Smart Chunk Size

DocAnalyser automatically sets the optimal chunk size based on your model:

| Model Context Window | Chunk Size | Example Models |
|---------------------|------------|----------------|
| 64K+ tokens | Large | Llama 3.2, Llama 3.1, Qwen 2.5 |
| 32K tokens | Medium | Mistral 7B |
| 8K tokens | Small | Gemma 2 |
| 4K tokens | Tiny | Phi-3 Mini |

*You don't need to change any settings - it's automatic!*

---

## Recommended Models by Computer Specs

| Your RAM | Recommended Model | Download Size | Speed | Quality |
|----------|------------------|---------------|-------|---------|
| 8 GB | Llama 3.2 1B | 1.3 GB | ⚡⚡⚡ Very Fast | ⭐⭐ Basic |
| 16 GB | **Llama 3.2 3B** | 2.0 GB | ⚡⚡⚡ Fast | ⭐⭐⭐ Good |
| 16 GB | Phi-3 Mini | 2.3 GB | ⚡⚡⚡ Fast | ⭐⭐⭐ Good |
| 24 GB | Mistral 7B | 4.1 GB | ⚡⚡ Medium | ⭐⭐⭐⭐ Very Good |
| 32 GB | **Llama 3.1 8B** | 4.7 GB | ⚡⚡ Medium | ⭐⭐⭐⭐⭐ Excellent |
| 32 GB | Qwen 2.5 7B | 4.4 GB | ⚡⚡ Medium | ⭐⭐⭐⭐⭐ Excellent |
| 48 GB+ | Qwen 2.5 14B | 9.0 GB | ⚡ Slower | ⭐⭐⭐⭐⭐ Excellent |

**Best choices for most users**:
- **Budget/older PC**: Llama 3.2 3B - fast and capable
- **Modern PC (32GB)**: Llama 3.1 8B - excellent quality, good speed
- **Reasoning tasks**: DeepSeek R1 7B - specialised for analysis

---

## Using Local AI in DocAnalyser

Once configured, using local AI is exactly the same as using cloud AI:

1. Load your document (YouTube video, PDF, etc.)
2. In the main window, set **AI Provider** to **"Ollama (Local)"**
3. Select your model from the **AI Model** dropdown
4. Select your prompt
5. Click **Run**

The status bar will show the chunk size being used (e.g., "🦙 Model has 128K context - using Large chunks").

---

## Ollama vs LM Studio

DocAnalyser supports both Ollama and LM Studio. Here's why we recommend Ollama:

| Feature | Ollama | LM Studio |
|---------|--------|-----------|
| **Setup** | ✅ Simpler - runs in background | Requires manual server start |
| **Model Loading** | ✅ Automatic | Manual - must load model each time |
| **Reliability** | ✅ More stable | Can have connection issues |
| **Resource Use** | ✅ Lighter | Heavier UI |
| **Model Selection** | Good selection | Wider selection |

**LM Studio** is still available in DocAnalyser if you prefer it or need models not available in Ollama.

---

## Troubleshooting

### "Ollama is not installed"
- Download Ollama from https://ollama.com
- Run the installer
- Restart DocAnalyser

### "Ollama server is not running"
- **Windows**: Look for the Ollama icon in the system tray (bottom right). If not there, search for "Ollama" in the Start menu and run it.
- **Mac**: Look for Ollama in the menu bar. If not there, open Ollama from Applications.
- **Linux**: Run `ollama serve` in a terminal.

### "No models installed"
- Open the Local AI Setup wizard in DocAnalyser
- Select a model and click Download
- Or use terminal: `ollama pull llama3.2:3b`

### Models Not Appearing in Dropdown
- Click **Refresh Models** in Settings
- Make sure Ollama is running (check system tray)
- Try restarting DocAnalyser

### Very Slow Generation
- Try a smaller model (3B instead of 7B)
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

## Command Line (Optional)

If you prefer using the terminal, Ollama has simple commands:

```
ollama pull llama3.2:3b     # Download a model
ollama list                  # See installed models
ollama rm llama3.2:3b       # Delete a model
ollama run llama3.2:3b      # Test a model interactively
```

---

## Quick Reference: Cloud vs Local

| Aspect | Cloud API | Local (Ollama) |
|--------|-----------|----------------|
| **Privacy** | Data sent to provider | 🔒 Completely private |
| **Cost** | Pay per use | 🆓 Free after setup |
| **Speed** | ⚡ Fast (5-15 sec) | Slower (15-60 sec) |
| **Quality** | ⭐⭐⭐⭐⭐ Excellent | ⭐⭐⭐-⭐⭐⭐⭐⭐ Good to Excellent |
| **Internet** | Required | Not required |
| **Setup** | Just need API key | Install Ollama + download model |

---

## Recommended Workflow

For users who want privacy but also need speed occasionally:

1. **Daily summarisation tasks** → Use Ollama with Llama 3.2 3B (fast, private)
2. **Complex analysis** → Use Ollama with Llama 3.1 8B or DeepSeek R1
3. **Time-critical work** → Switch to a cloud provider temporarily
4. **Sensitive/confidential documents** → Always use local

DocAnalyser makes it easy to switch between providers - just change the dropdown.

---

## Getting Help

- **Ollama Documentation**: https://ollama.com/library
- **Ollama GitHub**: https://github.com/ollama/ollama
- **DocAnalyser**: Right-click any button for context-sensitive help

---

## Summary: Your Setup Checklist

- [ ] Download and install Ollama from https://ollama.com
- [ ] Open DocAnalyser → Settings → 🤖 Local AI Setup
- [ ] Download a recommended model (Llama 3.2 3B is a great start)
- [ ] Select "Ollama (Local)" as your AI Provider
- [ ] Select your model and run a prompt!

**That's it!** DocAnalyser handles chunk sizes, model loading, and connections automatically.

---

*Guide version 2.0 - January 2026*
*For DocAnalyser v1.2.0 (Beta)*
