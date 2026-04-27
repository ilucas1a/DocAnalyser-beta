# Voice-Based Speaker Identification — Segmentation Test Plan

**Date:** 27 April 2026
**Status:** Test plan — execute before any architectural commitments
**Related:** Enhancement 25 (Local Voice-Based Speaker Identification), Roadmap Phase B
**Predecessor conversation:** "Local audio transcription speaker diarisation workarounds" (24 April 2026)

---

## 1. Purpose

This document defines a structured evaluation of segmentation engines for DocAnalyser's local speaker-identification pipeline (Enhancement 25). It exists because the current pyannote-audio segmentation step has been shown empirically to overwhelm a "relatively capable" laptop, and the design cannot proceed until a workable replacement is identified.

The voiceprint identification layer (CAM++ via sherpa-onnx) is *not* in question — it is independently known to be light, accurate, and CPU-friendly, and is treated as settled. The unknown is the upstream segmentation engine that decides "where does each speaker's turn begin and end." That choice gates the whole feature.

This plan does not commit any architectural changes. It is purely an evaluation exercise whose outputs feed into the formal Enhancement 25 design document.

---

## 2. Overarching objectives

The pipeline being designed must support:

1. Maximum reduction in the manual editing burden of turning a locally-extracted audio transcript into a clean, edited transcript — speaker labelling being the largest single component of that burden.
2. Efficient operation on modestly powered PCs without dependence on cloud AI for any feature on the critical path of producing a reasonable transcript.
3. Heuristic logic in preference to AI logic wherever this makes sense, especially for deterministic structural decisions like paragraph boundaries at speaker changes, sentence splits at punctuation, and find/replace corrections.
4. Seamless integration with the existing `transcript_cleaner.py` → `diarization_handler.py` → `transcript_cleanup_dialog.py` pipeline, so the selected candidate can drop into the existing Phase 5 slot in `transcript_cleaner.clean_transcript()` without architectural surgery.

These are the fixed objectives against which every candidate is measured.

---

## 3. Hardware envelope

The "modestly powered" target needs concrete numbers so pass/fail is unambiguous:

- **Primary target hardware:** 16 GB RAM, no dedicated GPU, modern x86-64 CPU (4+ cores, no specific generation requirement).
- **Stretch target hardware:** 8 GB RAM, no GPU. Failure to meet stretch is acceptable; failure to meet primary disqualifies the candidate.
- **Ian's test laptop:** treated as a representative primary-target machine. Specs to be recorded at the start of testing for the report.

The pyannote-audio reference baseline already failed on the primary-target machine, so the bar is set by what comparable *lighter* engines can achieve on the same hardware running the same audio.

---

## 4. Test corpus

A test corpus drawn from real recordings the user is likely to encounter, not synthetic or curated benchmark audio. Six recordings, covering the realistic range of input quality and complexity:

1. **Clean two-speaker interview, ~5 minutes.** Fast iteration sample. Used for setup verification and quick comparisons.
2. **Clean two-speaker interview, ~30 minutes.** Mid-length sample at the workhorse duration.
3. **Clean two-speaker interview, ~60 minutes.** Long-form sample. The duration at which compute-cost differences become operationally meaningful.
4. **Archival-quality two-speaker recording.** Older, lower fidelity, possibly mono, possibly with background noise — representative of what an oral historian working with legacy material faces.
5. **Three-speaker recording or panel discussion, any length available.** Tests behaviour beyond the two-speaker sweet spot.
6. **Recording with rapid back-and-forth, e.g. interruptions or overlapping speech.** Stresses speaker-change detection.

If items 4–6 are not readily available, the test proceeds with items 1–3 alone; the missing cases are documented as evaluation gaps to revisit later.

All test recordings stay on the user's local filesystem. No audio leaves the machine at any point during testing.

---

## 5. Candidates

Three candidates plus one fallback, in order of preference:

### Candidate A — sherpa-onnx OfflineSpeakerDiarization (drop-in replacement)

The most direct substitute for the current pyannote-audio path. Uses the same pyannote-segmentation-3.0 model converted to ONNX format, plus a 3D-Speaker embedding model for clustering, run through ONNX Runtime instead of PyTorch.

- **Package:** `sherpa-onnx` (~4 MB Python wheel)
- **Models:** sherpa-onnx-pyannote-segmentation-3-0 (~5–6 MB) + 3dspeaker_speech_eres2net_base_sv (~30–35 MB)
- **API:** `OfflineSpeakerDiarizationConfig` / `Process(samples)` returning timeline of (start, end, speaker_id)
- **Dependencies:** ONNX Runtime only. No PyTorch, no CUDA, no HuggingFace token required at runtime.
- **Why first:** like-for-like swap of the segmentation engine, minimal code change in `diarization_handler.py`, identical output schema. If this passes, it answers the question without further investigation.

### Candidate B — Silero VAD + CAM++ embedding clustering (lightweight)

A custom pipeline using a voice activity detector to chop audio into speech regions, then CAM++ embeddings clustered with simple agglomerative clustering to assign speaker IDs.

- **Packages:** `silero-vad` (PyPI, ~10 MB including the model) + `sherpa-onnx` (already needed for CAM++)
- **Models:** Silero VAD (small, ~5–10 MB) + CAM++ (~7 MB)
- **Dependencies:** ONNX Runtime, NumPy, SciPy (for clustering). All standard, all light.
- **Why second:** smallest possible footprint. Likely to run comfortably even on the stretch target. Slightly less robust at speaker-change detection than a dedicated neural segmenter, but oral history interviews are typically two speakers with clear turn boundaries — it may be enough.

### Candidate C — webrtcvad + CAM++ embedding clustering (featherweight)

Same architecture as Candidate B, but using the Google webrtcvad library (the original lightweight VAD used in WebRTC) instead of Silero. Distinctly older technology, less accurate at speech/non-speech detection in noisy recordings, but very small and battle-tested.

- **Packages:** `webrtcvad` (tiny — under 1 MB) + `sherpa-onnx`
- **Why third:** included as a fallback if both A and B exceed the stretch-target memory budget. Unlikely to be the winner but worth knowing whether it works.

### Candidate D (deferred) — Falcon

Mentioned briefly in the 24 April conversation as a lighter pyannote alternative. Not investigated in depth at the time. Included here as a placeholder to revisit if A, B, and C all fail. Unlikely to be needed.

---

## 6. Metrics

For every (candidate × recording) pair, capture:

### Resource metrics (objective, machine-measurable)

- **Peak RSS memory** during diarisation, in MB. Captured via `psutil.Process().memory_info().rss` polled every 200 ms during the run.
- **Wall-clock processing time** in seconds.
- **Real-time factor (RTF):** processing time divided by audio duration. RTF of 1.0 means the diarisation took as long as the recording; RTF of 0.3 means three times faster than real-time.
- **Crash/freeze flag:** boolean. If the process is killed, swaps heavily, or wedges the machine, the candidate fails this recording regardless of other metrics.
- **Setup time:** model download time on first run (one-off, not on the critical path but worth recording).

### Quality metrics (subjective, requires manual review)

True diarisation error rate (DER) requires hand-labelled ground truth and is too academic for this purpose. We use a practical proxy aligned with the actual user-editing workload:

- **Speaker boundaries correct:** for each transcript paragraph the segmenter produces, was the assigned speaker correct? Counted as a percentage of paragraphs needing speaker correction during manual review.
- **Missed speaker changes:** count of places where the audio clearly switches speakers but the segmenter kept it as one cluster.
- **Spurious speaker changes:** count of places where one speaker was split across multiple clusters (over-segmentation).
- **Subjective usability score (1–5):** would the user tolerate this in production? 5 = "ship it"; 3 = "usable with editing"; 1 = "worse than current behaviour".

The quality metrics are gathered by the user opening each output transcript in DocAnalyser's existing SpeakerPanel and noting corrections that would be needed.

---

## 7. Pass / fail thresholds

Each candidate must clear all five thresholds on the primary-target hardware to advance:

1. **Peak RAM ≤ 1.5 GB** during diarisation. Above this, the pipeline crowds out DocAnalyser, Word, and the companion player on a 16 GB machine.
2. **RTF ≤ 2.0** on a 60-minute recording. A 60-minute interview must complete in 2 hours or less of compute. Privacy-sensitive users tolerate time delays; multi-hour delays per recording are still tolerable for end-of-day batch use.
3. **No crashes, freezes, or heavy swap** on any test recording.
4. **Manual speaker correction needed on ≤ 30% of paragraphs** for clean two-speaker recordings (items 1–3 in the corpus).
5. **Subjective usability ≥ 3** on every test recording.

Stretch-target thresholds (8 GB RAM machine), recorded but not gating:

- **Peak RAM ≤ 1.0 GB**
- **RTF ≤ 3.0** on a 60-minute recording

---

## 8. Test procedure

A single Python harness script runs all candidates against all recordings in a deterministic, repeatable way. Outputs are written to a results directory for review.

### 8.1 Setup (once)

1. Create an isolated Python virtual environment under `C:\Ian\Python\Voice_ID_Test\` (separate from the DocAnalyser venv, to avoid polluting the production environment until a winner is chosen).
2. Install the candidate packages: `sherpa-onnx`, `silero-vad`, `webrtcvad`, plus `psutil`, `numpy`, `scipy`, `soundfile`, `librosa` for resource monitoring and audio handling.
3. Download the required ONNX models into a `models/` subdirectory. Record total disk footprint.
4. Place test corpus recordings in a `corpus/` subdirectory.
5. Verify each candidate's "hello world" works on the 5-minute test recording before proceeding.

### 8.2 Per-candidate run

For each candidate × each recording:

1. Restart Python to flush any cached state.
2. Start the resource monitor in a background thread (samples peak RSS every 200 ms).
3. Load audio, run the candidate's diarisation function, collect the speaker timeline.
4. Stop the resource monitor; record peak RSS, wall-clock time, RTF.
5. Write the speaker timeline out as a JSON file: `results/<candidate>/<recording>.json` with per-segment (start, end, speaker_id) tuples.
6. Write a row to `results/summary.csv` with the resource metrics.
7. If the run crashes or exceeds 4× audio duration, abort, log the failure, and continue to the next pairing.

### 8.3 Quality review (manual, after all runs complete)

For each candidate × each recording:

1. Open the speaker timeline JSON alongside the audio in any tool that lets the user scrub timestamps (DocAnalyser's companion player works fine).
2. Walk through the timeline against the audio, noting paragraph-level errors against the quality metrics above.
3. Record results in `results/quality_review.csv` with one row per (candidate, recording) pair.
4. Capture a brief subjective note ("worked well except for the section around 23 minutes where Speaker 2 was split into two clusters") for the report.

### 8.4 Decision

Compile a final report tabulating resource metrics + quality metrics for all candidates. Apply the pass/fail thresholds. Produce a recommendation in plain English: "Candidate A passes on all metrics; recommend adopting it. Candidate B passes on resource metrics but fails quality thresholds on archival audio; recommend as fallback for memory-constrained users." Or whatever the data actually says.

---

## 9. Test harness specification

The harness is a single Python file, `test_diarisation.py`, with the following structure:

- **Candidate adapters:** one function per candidate, each conforming to a uniform interface `diarise(audio_path: str) -> List[Tuple[float, float, str]]`. This isolates the candidate-specific code and makes adding a fourth candidate trivial.
- **Resource monitor:** a small class that runs in a background thread, polls `psutil.Process().memory_info().rss` at 200 ms intervals, and reports peak.
- **Runner:** iterates the candidate × recording matrix, calls each adapter, captures resources and timing, writes outputs.
- **CLI:** `python test_diarisation.py --candidate A --recording short` for spot-checks during development; `python test_diarisation.py --all` for the full sweep.

The harness does not import anything from DocAnalyser. It is fully self-contained in the test virtual environment so DocAnalyser's runtime is not touched until a winning candidate is integrated.

The harness will be written as the next step after this plan is approved.

---

## 10. Voice-ID layer evaluation (parallel, not blocking)

The CAM++ identification layer can be tested independently of the segmentation choice, because CAM++ takes a speech segment as input and produces a 512-dimensional voiceprint regardless of how that segment was bounded. A small parallel test confirms it works on the target hardware:

1. Pick three speakers from the test corpus. For each, extract a clean 15-second sample manually using any audio editor.
2. Run each through CAM++ to produce a voiceprint vector.
3. For each test recording's diarised clusters, sample 2–3 segments per cluster, embed them with CAM++, average the embeddings, and compute cosine similarity against the three enrolled voiceprints.
4. Verify that clusters dominated by enrolled speakers match their voiceprint at high similarity (typically > 0.7 on cosine), and that clusters dominated by unenrolled speakers don't match any voiceprint above the threshold.
5. Record peak RAM and processing time for the embedding step.

Expected result based on prior literature: sub-second per segment, peak RAM well under 200 MB, similarity scores > 0.8 for matched speakers and < 0.5 for unmatched. If this holds, the identification layer is confirmed feasible and the open question reduces to the segmentation choice alone.

---

## 11. Out of scope for this test

To keep the test focused, the following are explicitly *not* covered and are deferred to the formal Enhancement 25 design:

- The user-facing enrollment dialog (prospective and retrospective modes).
- The SpeakerPanel UX changes that surface match confidence and the merge-suggestion logic.
- The SQLite schema for the speakers and document_speaker_matches tables.
- The voiceprint update policy (lock at first enrollment vs running average).
- Confidence threshold defaults for auto-confirm vs prompt-for-review.
- PyInstaller bundling of the new packages and models.
- Integration with the AssemblyAI cloud diarisation path (which already works and is unaffected by this).
- Any AI-assisted features from the v3 transcript-refinement spec — that work is paused pending the outcome of this test, since a working local speaker-ID layer changes the role of AI in the pipeline significantly.

---

## 12. Estimated effort

- **Test harness writing:** 0.5–1 day. Mostly straightforward — three adapters, a resource monitor, a runner, output writers.
- **Setup and dependency installation:** 1–2 hours, plus model download time.
- **Test corpus assembly:** dependent on what Ian has on hand. If suitable recordings are already available, an hour. If not, source recordings need to be located.
- **Running the full sweep:** dominated by audio duration. The 5-minute, 30-minute, and 60-minute clean recordings alone are 95 minutes of audio; with three candidates and assumed RTF averages around 1.0, that's roughly 5 hours of compute time spread across the runs. Can run unattended.
- **Manual quality review:** 30 minutes per (candidate × recording) pair, so roughly 9 hours total for three candidates × six recordings. Probably the longest single component.
- **Report compilation and recommendation:** 0.5 day.

**Total elapsed time:** about a week of part-time work, with most of the manual review work parallelisable across multiple sittings.

---

## 13. Decision logic

The test produces one of four outcomes:

1. **Candidate A passes all thresholds.** Recommendation: adopt sherpa-onnx OfflineSpeakerDiarization as a drop-in replacement for pyannote-audio in `diarization_handler.py`. Re-enable the pipeline. Move directly to the formal Enhancement 25 design document. This is the expected outcome.

2. **Candidate A fails on RAM or RTF; Candidate B passes.** Recommendation: adopt the Silero VAD + CAM++ + agglomerative clustering pipeline. Note the trade-off (slightly worse on rapid-turn detection) in the design document and add a tier-2 setting that lets users on capable hardware optionally use Candidate A's heavier path if they have it available.

3. **Both A and B fail; Candidate C passes.** Recommendation: ship with webrtcvad + CAM++ for the lightest possible footprint, with documented quality limitations. Revisit Candidate D (Falcon) as a possible upgrade path.

4. **All three fail.** Recommendation: pause Enhancement 25, document findings, fall back to manual SpeakerPanel as the local-only path. Investigate Falcon and any newer alternatives that have emerged. This outcome is not expected based on the architecture analysis but must be acknowledged.

---

## 14. Implications for the AI Transcript Refinement spec (v3)

If Enhancement 25 lands, the v3 spec's tickbox 4.5 ("Assign speakers") shrinks substantially. Speaker assignment becomes upstream of the AI refinement step, mostly automated, with the AI's role reduced to re-attributing the small number of paragraphs the voice-ID layer flags as low-confidence. This is a simplification of the v3 spec, not a contradiction of it.

It also strengthens the case made in the 26–27 April discussion for treating the v3 panel as a *local-first foundation* with cloud-AI features as an optional layer on top. With local speaker-ID working, a privacy-bound user gets a usable transcript with correct speaker labels using nothing but local heuristics + Corrections Lists + voice-ID — no cloud AI required at any step on the critical path. The cloud-AI features become genuinely additive rather than load-bearing.

The v3 spec is therefore on hold pending the outcome of this test, and will be revisited in light of the result.

---

*Test plan drafted by Claude in collaboration with Ian Lucas, 27 April 2026.*
*Execution to follow upon Ian's review and approval.*
