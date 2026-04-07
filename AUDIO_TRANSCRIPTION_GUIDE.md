# Audio Transcription Guide

## A Guide for Oral Historians and Researchers Using DocAnalyser

This guide explains how to transcribe recorded interviews and other audio using DocAnalyser — what your options are, how they compare, and how to get the best results from your recordings.

---

## What Is Audio Transcription?

Audio transcription converts spoken words in a recording into written text automatically. Instead of listening to a recording and typing what you hear — which typically takes three to five hours for every hour of audio — transcription software analyses the audio and produces a text document in minutes.

DocAnalyser goes further than producing a plain transcript. It:

- Adds a visible timestamp to every paragraph, and tracks every individual sentence so that clicking any sentence in the transcript seeks the audio to that exact point
- Includes a built-in audio player so you can listen to the recording and read the transcript side by side — making it easy to check the accuracy of the transcription, correct mistakes, and identify who is speaking
- Provides speaker identification: AssemblyAI (cloud) identifies speakers automatically and reliably; Faster-Whisper (local) offers provisional suggestions based on text patterns that will need review; OpenAI Whisper (cloud) does not identify speakers. In all cases, DocAnalyser includes a speaker identification panel that makes it easy to work through the transcript manually — using the built-in audio player to listen to each passage before confirming or correcting the assignment
- Cleans up the raw transcript — removing the "ums", "uhs", and false starts that appear when speech recognition is very literal
- Links AI-generated summaries directly back to the moments in the audio they describe, so you can click a point in a summary and hear that section of the recording

---

## Why This Matters for Oral History

Oral history recordings are irreplaceable primary sources. A verbatim transcript is important both as a research tool and as a preservation record. The problem has always been the time cost: a skilled transcriber working at normal pace produces roughly 15 minutes of finished transcript per hour of work. A 90-minute interview can take six hours or more to transcribe manually.

Automatic transcription is not perfect — it will mishear names, stumble on accents, and occasionally produce nonsense — but for clear recordings in standard accents it typically gets you 85–95% of the way there in minutes rather than hours. For recordings with strong regional accents, non-English words or phrases, personal or place names, and specialist vocabulary (all common in oral history recordings), accuracy will be lower and more correction will be needed — but even a 70% accurate automatic transcript is a substantial foundation compared to starting from silence. The remaining corrections are far faster to make than transcribing from scratch.

Beyond speed, DocAnalyser's transcription is designed with a specific concern of oral historians in mind: **the privacy and sensitivity of community recordings**. Many oral history recordings contain personal, cultural, or politically sensitive material that the community would not want sent to a commercial cloud service. DocAnalyser's local transcription option keeps your recordings entirely on your own computer.

---

## Your Transcription Options in DocAnalyser

DocAnalyser supports three transcription engines. Each has different strengths.

---

### Option 1: Faster-Whisper — Local, Free, and Private

Faster-Whisper is an open-source speech recognition system that runs entirely on your own computer. Nothing is uploaded anywhere.

**How it works**: On first use, DocAnalyser downloads the transcription model to your computer (approximately 140 MB for the standard model). After that, it works offline with no ongoing cost.

**Quality**: Very good for clear recordings in standard accents with single or two speakers. Handles most English accents reasonably well. Accuracy is lower for strong regional accents, overlapping speech, background noise, or recordings that include Indigenous language terms, personal names, or specialist vocabulary unfamiliar to the model.

**Speed**: On a modern computer, roughly 3–6 times faster than real time. A 30-minute recording typically takes 5–10 minutes to transcribe. Faster if your computer has an NVIDIA graphics card.

**Speaker identification**: Faster-Whisper itself does not distinguish between speakers. DocAnalyser adds a heuristic analysis layer that labels paragraphs as SPEAKER_A and SPEAKER_B based on patterns in the text — questions and short responses are assigned to the interviewer, longer passages to the interviewee. These labels are clearly marked as suggestions and may need correction, which you can do using the speaker identification panel in DocAnalyser.

**Best for**:
- Sensitive or confidential community recordings
- Regular project work where ongoing cloud costs would add up
- Working offline or in locations without reliable internet
- Large archives where you need to process many recordings

**Cost**: Free after the initial model download.

---

### Option 2: OpenAI Whisper — Cloud, Fast, Accurate

OpenAI Whisper sends your audio file to OpenAI's servers for transcription and returns the result. It uses the same underlying technology as Faster-Whisper but runs on powerful cloud hardware.

**Quality**: Excellent. One of the most accurate general-purpose transcription systems available. Handles accents, variable audio quality, and longer recordings well. Still susceptible to errors with uncommon names and specialist vocabulary, but generally more robust than the local option on difficult recordings.

**Speed**: Very fast — typically 30–60 seconds for a 30-minute interview, regardless of your computer's hardware.

**Speaker identification**: Not available. The transcript is returned as continuous text without speaker labels.

**Privacy**: Your audio file is sent to OpenAI's servers. OpenAI does not use API-submitted audio to train its models (as of 2026), but the audio does leave your computer. Not suitable for recordings where community consent was given on the understanding that material would remain private.

**Cost**: Approximately $0.006 per minute of audio — around 18 cents for a 30-minute interview, or $1.08 for a 3-hour recording. Requires an OpenAI API key (the same one used for ChatGPT analysis).

**Best for**:
- Quick, high-quality transcription of non-sensitive recordings
- One-off transcriptions where speed matters
- Difficult recordings that Faster-Whisper struggled with

---

### Option 3: AssemblyAI — Cloud, Speaker Identification

AssemblyAI is a specialist transcription service with particularly strong speaker identification ("diarization") — the ability to reliably determine who is speaking throughout a recording.

**Quality**: Excellent accuracy, comparable to OpenAI Whisper. Speaker identification is significantly more reliable than heuristic methods, especially for recordings where the two speakers have similar speaking styles or where the interviewer speaks at length.

**Speed**: Similar to OpenAI Whisper — most 30-minute recordings return in under a minute.

**Speaker identification**: Automatic and reliable. AssemblyAI returns the transcript with each paragraph labelled by speaker — SPEAKER_A, SPEAKER_B, and so on. DocAnalyser then lets you replace these labels with the speakers' real names.

**Privacy**: Your audio is sent to AssemblyAI's servers. Same privacy considerations as OpenAI Whisper — not suitable for recordings that must remain on your own computer.

**Cost**: Approximately $0.015 per minute — around 45 cents for a 30-minute interview, or $2.70 for a 3-hour recording. Requires an AssemblyAI API key (free to sign up, pay only for what you use).

**Best for**:
- Interviews where accurate speaker attribution is important from the start
- Recordings where the two speakers are difficult to distinguish by pattern alone
- Professional or archival work where speaker labels need to be reliable

---

## Comparing Your Options

| | Faster-Whisper (Local) | OpenAI Whisper (Cloud) | AssemblyAI (Cloud) |
|---|---|---|---|
| **Privacy** | 🔒 Completely private | Sent to OpenAI | Sent to AssemblyAI |
| **Cost** | Free | ~$0.006/min | ~$0.015/min |
| **Speed** | 3–6× real time | ~30–60 sec/recording | ~30–60 sec/recording |
| **Quality** | Very good | Excellent | Excellent |
| **Speaker ID** | Heuristic (needs checking) | Not available | Automatic and reliable |
| **Internet** | Not required | Required | Required |
| **Setup** | Download model (~140 MB) | API key only | API key only |

---

## What DocAnalyser Does After Transcription

When transcription completes, DocAnalyser offers a cleanup step before saving the transcript. This step is optional but strongly recommended.

### Cleanup

Raw speech recognition output contains a great deal of noise — very short fragments ("uh", "um", brief pauses captured as separate entries), listener back-channels ("mm-hmm", "right"), and fragmented sentences. The cleanup pipeline:

1. **Removes breath fragments** — strips out "um", "uh", "hmm" and similar filler words that were captured as separate entries
2. **Keeps listener back-channels as annotations** — short responses from the listener ("mm-hmm", "right", "yes") are retained in the text as bracketed annotations [Mm-hmm] rather than discarded, because they mark where the speaker was acknowledged and can be meaningful in an oral history context
3. **Joins fragments into sentences** — consecutive short segments that belong to the same utterance are joined into complete sentences
4. **Groups sentences into paragraphs** — using timing gaps and speaker changes as boundaries, so each paragraph block belongs to a single speaker

### Timestamps

Every paragraph carries a timestamp showing where it occurs in the recording. These are clickable — clicking a paragraph in DocAnalyser's transcript viewer seeks the audio player directly to that point in the recording.

### Audio-Linked Summaries

Once you have a cleaned transcript, you can ask DocAnalyser's AI to produce a summary where each key point is linked to the moment in the recording where it was said. In the Thread Viewer, these appear as blue "▶ Jump to MM:SS" links that seek the audio player directly to the relevant passage. This makes it possible to navigate long interviews by topic rather than having to listen from the beginning.

---

## From Transcript to Analysis — Where DocAnalyser Really Pays Off

Producing the transcript is only the first step. Once your recording is in DocAnalyser, the full power of AI analysis becomes immediately available — applied directly to the material in front of you, with links back to the audio.

You can ask the AI to:

- **Extract key themes** across a single interview or a set of interviews
- **Identify the most significant passages** for a particular research question
- **Produce a structured summary** suitable for an archive description or research note
- **Find every mention of a specific topic, person, or place** across multiple transcripts
- **Compare what different narrators say** about the same events or themes
- **Generate questions** that would be worth exploring in follow-up interviews

These analyses are stored alongside the transcript in DocAnalyser's Documents Library. You can return to them, run different prompts against the same transcript, or compare the same prompt across a set of interviews. Clicking any timestamp link in an AI-generated summary takes you directly to the corresponding moment in the recording.

This capability — moving fluidly between audio, transcript, and AI analysis in a single integrated workflow — is what distinguishes DocAnalyser from using a transcription service and an AI chat interface separately.

---

## Speaker Identification in Detail

Speaker identification in DocAnalyser works at two levels.

### Level 1 — Heuristic Labels (Automatic, Free, Built-in)

After cleanup, DocAnalyser analyses the text of each paragraph to assign provisional speaker labels. The logic is based on patterns common in oral history interviews:

- Paragraphs ending with a question mark are likely the interviewer
- Very short paragraphs following a long passage are likely the interviewer interjecting
- Long continuous passages are likely the interviewee

These labels are marked as "suggested" throughout the interface. They are a reasonable starting point — often 80–90% correct for a structured interview — but will need review, particularly where the interviewer speaks at length or where the conversation is less structured.

### Level 2 — Click-to-Identify Panel (Manual, Built-in)

The speaker identification panel in the Thread Viewer lets you work through the transcript paragraph by paragraph, clicking a speaker name to confirm or correct each assignment. You can:

- Jump to the audio for any paragraph to listen before assigning
- Use "Identify all" to bulk-apply the heuristic labels wherever you are confident they are correct, then manually correct only the uncertain cases
- Assign real names (e.g. "Margaret Pearce" and "Interviewer") that replace the machine labels throughout the transcript

### Level 3 — Voice Recognition (Future Feature)

DocAnalyser includes support for pyannote.audio, a voice-based speaker recognition system that identifies speakers by the acoustic properties of their voice rather than the patterns in the text. This is significantly more accurate for recordings where the two speakers have similar styles, or for multi-speaker recordings.

This feature requires a HuggingFace account and a one-time model download, and is computationally demanding. It is not currently enabled in this version, but will be available in a future release once hardware requirements have been assessed for typical community researcher computers.

---

## A Typical Workflow

**1. Load the audio file**
Drag your MP3, WAV, or M4A file into DocAnalyser's input field, or click Browse and navigate to it.

**2. Choose your transcription settings**
Click the Audio Settings button to select your transcription engine and configure options (language, speaker identification for AssemblyAI).

**3. Click Transcribe Audio**
DocAnalyser transcribes the recording and shows you the text as it is processed, paragraph by paragraph.

**4. Review the cleanup dialog**
When transcription is complete, a cleanup dialog appears. Tick the options you want — fragment removal is always recommended. If you want speaker suggestions, select "Suggest speakers automatically". Click "Clean up transcript".

**5. Review and correct speaker labels**
Open the Thread Viewer. The built-in audio player appears at the top of the window. Click any sentence in the transcript to seek the player to that point, then use the Play button to hear what was said. This makes it straightforward to confirm who is speaking and check the accuracy of the transcription before finalising. Click "🏷 Identify" to open the speaker identification panel and work through the assignments.

**6. Run AI analysis**
With the transcript loaded, select a prompt from the Prompts Library (or write your own) and click Run. The AI analyses the transcript and returns a response with key themes, summaries, or answers to your research questions. For audio-linked summaries, select the "Audio-Linked Summary" prompt — the response will contain timestamped links back to the recording.

**7. Save and export**
Everything is saved automatically to your Documents Library. You can export the transcript, the AI analysis, or the complete conversation thread to Word, PDF, or plain text.

---

## Audio Quality Tips

The quality of transcription depends heavily on the quality of the recording.

**What helps most**:
- Recording in a quiet room with minimal background noise
- A dedicated interview microphone rather than a phone or laptop built-in mic
- Positioning the microphone between the two speakers, not close to one only
- Asking speakers to avoid talking over each other — brief pauses between turns significantly improve accuracy

**What causes problems**:
- Background noise (traffic, music, air conditioning fans)
- Recordings where one speaker is much louder than the other
- Very strong regional accents or non-standard speech patterns
- Personal names, place names, and specialist vocabulary not in the model's training
- Recordings with more than two speakers in simultaneous conversation

**If quality is poor**:
OpenAI Whisper and AssemblyAI tend to handle difficult recordings better than Faster-Whisper, because they run on more powerful hardware. For important recordings that did not transcribe well locally, consider running them through AssemblyAI even if you would normally use the local option.

---

## Supported Audio and Video Formats

DocAnalyser accepts audio and video files directly. Video files have their audio track extracted automatically.

| Format | Type |
|--------|------|
| .mp3 | Most common audio format |
| .wav | Uncompressed audio |
| .m4a | Apple audio format (iPhone recordings) |
| .ogg | Open audio format |
| .flac | Lossless compressed audio |
| .aac | Compressed audio |
| .mp4 | Video (audio extracted) |
| .mov | Apple video (audio extracted) |
| .avi | Video (audio extracted) |

---

## Practical Recommendations by Scenario

**Community recordings with sensitive cultural content**
→ Use Faster-Whisper (local). Accept the heuristic speaker labels as a starting point and use the identification panel to correct them. The recording never leaves your computer.

**Professional interview for publication, two speakers**
→ Use AssemblyAI. Speaker identification will be reliable from the start, minimising manual correction. Review the transcript for accuracy before using in any published work.

**Quick reference transcript, not for archiving**
→ Use OpenAI Whisper. Fast, accurate, and the cheapest cloud option. No speaker identification, but adequate for a working reference copy.

**Large archive project — hundreds of recordings**
→ Use Faster-Whisper for the bulk of the work. Set up the cleanup options to your preference and process recordings one at a time or in batches using DocAnalyser's Bulk Import feature. Reserve AssemblyAI for recordings where speaker identification is particularly important.

**Working in a location with no internet**
→ Faster-Whisper only. Ensure the model has been downloaded before you leave — check Audio Settings to confirm the model is available locally.

---

## Quick Reference: Transcription Settings in DocAnalyser

All transcription settings are in **Audio Settings** (via the Settings button or alongside the Transcribe Audio button):

| Setting | What It Does |
|---------|-------------|
| **Engine** | Choose Faster-Whisper, OpenAI Whisper, or AssemblyAI |
| **Language** | Leave on Auto-detect for most recordings; specify if detection fails |
| **Speaker identification** | AssemblyAI only: enable diarization for automatic speaker labels |
| **VAD (Voice Activity Detection)** | Filters out silent passages; recommended for recordings with long pauses |
| **Timestamp interval** | How frequently timestamps appear in the output text |
| **Bypass cache** | Forces re-transcription if you have changed settings and want a fresh result |

---

*Guide version 1.1 — March 2026*
*For DocAnalyser v1.4.0 (Beta)*
