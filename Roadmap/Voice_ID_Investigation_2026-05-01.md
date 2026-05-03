# Voice-Based Speaker Identification — Investigation Log

**Date:** 1 May 2026
**Status:** Investigation closed — Enhancement 25 not viable as a local-first feature
**Predecessor:** `Roadmap/Voice_ID_Segmentation_Test_Plan_2026-04-27.md`
**Outcome:** AssemblyAI remains the production diarisation path. No new code or architectural change in DocAnalyser.

---

## 1. TL;DR

Three lightweight local-diarisation candidates were evaluated against the test plan dated 27 April 2026 over a single day's testing on the reference laptop. **None of the candidates met the §7 thresholds for a shippable local diarisation pipeline.** The decision is to close Enhancement 25 as investigated-and-not-viable, retain AssemblyAI as the cloud diarisation path, and preserve the findings here so the investigation does not need to be repeated.

The negative result is itself a useful engineering outcome: DocAnalyser now has a clear, evidence-backed answer to "should we ship local diarisation?" rather than a half-built feature.

---

## 2. Hardware context

Testing was performed on the reference laptop specified in the test plan §3 — Lenovo ThinkPad X1 Carbon Gen 13, Intel Core Ultra 7 258V, 32 GB RAM, with ONNX Runtime pinned to CPU-only execution per the harness specification. This machine sits well above the primary target (16 GB RAM, no GPU), so any failure here translates to a worse failure on typical user hardware.

---

## 3. Candidates evaluated

The three candidates from the test plan were considered in order of preference:

- **Candidate A — sherpa-onnx OfflineSpeakerDiarization** (pyannote-segmentation-3.0 in ONNX + 3D-Speaker eres2net embedding). The intended like-for-like swap of the segmentation engine.
- **Candidate B — Silero VAD + CAM++ embedding clustering.** Lightweight custom pipeline. The bulk of the day's testing focused here because it was the most promising lightweight option.
- **Candidate C — webrtcvad + CAM++.** Featherweight fallback. Not advanced past initial setup once Candidate B had produced a definitive negative result.

Candidate D (Falcon) was deferred per the test plan and not investigated.

---

## 4. Candidate B (Silero VAD + CAM++) — detailed findings

The bulk of the day was spent on Candidate B because it was the lightest credible architecture. The investigation followed two phases: a threshold sweep on the CAM++ embedding model, and an embedding-model swap to eres2net.

### 4.1 CAM++ threshold sweep

Agglomerative clustering threshold (cosine distance, 0..2 range) was swept against the short, medium, and long clean two-speaker test recordings (Tony + Chris):

| Threshold | Short | Medium | Long |
|---|---|---|---|
| 0.5 | 8 clusters @ 78.4% Top-2 | — | — |
| 0.7 | 4 clusters @ 87.5% Top-2 | 5 clusters @ 89.1% Top-2 | 7 clusters @ 68% Top-2 |
| 0.85 | — | — | 2 clusters @ 100% Top-2 *(but listen-test revealed both clusters were the same speaker — false collapse)* |

The 0.85 long-recording result is the critical failure mode: numerically the clusters look perfect, but the audio reveals over-merging. No single threshold worked across the three durations: low thresholds over-segmented (especially Chris's voice into many micro-clusters), high thresholds collapsed distinct speakers together.

### 4.2 eres2net embedding swap

To rule out CAM++'s discriminative power as the cause, the embedding model was swapped to 3D-Speaker eres2net (the same model used by Candidate A's clustering step). The clustering threshold was reset to the sherpa-onnx default of 0.5 and re-tuned from there.

**Short recording.** With eres2net, Tony and Chris were correctly separated. Listen-test confirmed clean speaker boundaries. Genuinely a working candidate at the short duration.

**Medium recording at threshold 0.5.** 165 clusters produced. Cluster mass distribution showed Tony's embeddings tightly grouped (SPEAKER_153 at 66.6% of speech) and Chris's voice fragmented into 163 micro-clusters with the largest Chris-fragment (SPEAKER_11) holding only 8.1%. Tony's within-speaker cosine distance stayed below 0.5; Chris's spread well above. The asymmetry — one speaker's voice fragmenting while the other clusters cleanly — is the core signal that the embedding is failing to capture Chris's voice consistently.

**Medium recording at threshold 0.85.** 3 clusters with the expected mass distribution. Listen-test verdict: the second cluster contained a mix of Tony and Chris. eres2net at this threshold merged Chris into Tony rather than merging Chris's fragments into one another. Same failure mode as CAM++ at high thresholds, in a different guise.

**Long recording at threshold 0.85.** 50+ clusters. Chris's fragments were too spread out across the recording for any reasonable threshold to recover. Definitive failure.

### 4.3 The pattern

Across two embedding models (CAM++ and eres2net) and the full threshold range, the same failure shape recurred: same-gender English speakers in clean two-speaker recordings could not be reliably discriminated by lightweight ONNX speaker embeddings combined with simple agglomerative clustering. There is no threshold and no embedding swap within this architecture that solves the problem, because the failure is in the embedding's discriminative power, not in the clustering parameters.

This rules out the entire Candidate B architecture for clean two-speaker oral history recordings — the dominant DocAnalyser use case.

---

## 5. Candidate A (sherpa-onnx OfflineSpeakerDiarization)

Candidate A — the dedicated neural segmenter using pyannote-segmentation-3.0 in ONNX format — failed during testing on the reference laptop. *(Specific failure mode and traceback to be captured here from the run logs if Ian wants this level of forensic detail in the record.)*

This mirrors the original pyannote-audio failure that motivated the whole investigation: the heavier neural-segmentation approach does not run reliably on the reference machine, let alone the typical user's hardware.

---

## 6. Candidate C (webrtcvad + CAM++)

Not advanced past initial setup. Given that:

- Candidate B (Silero VAD + CAM++) had produced a definitive negative result on the embedding-discrimination front, and
- Candidate C uses the *same* CAM++ embedding model, just with a more primitive VAD,

there was no plausible path by which Candidate C could pass thresholds Candidate B failed. The VAD layer affects where segments are cut, not whose voice is in them.

---

## 7. Conclusion

Lightweight ONNX speaker-embedding models combined with agglomerative clustering — the architecture every viable lightweight candidate in this space relies on — cannot discriminate same-gender English speakers in clean two-speaker recordings reliably enough for production use. The heavier alternative (pyannote-audio, or its ONNX surrogate inside Candidate A) does not run within the §7 hardware envelope on the reference machine.

There is no architecture in the candidate set that meets all six thresholds in the test plan §7. **Enhancement 25 is closed as investigated-and-not-viable.**

The production diarisation path remains AssemblyAI (cloud), as it was before the investigation began. AssemblyAI continues to deliver high-quality diarisation for users who accept the cloud trade-off; users who require local-only processing continue to use the existing manual SpeakerPanel, which is unaffected.

---

## 8. Implications for the v3 AI Transcript Refinement spec

The v3 spec was placed on hold pending this investigation due to the contradiction between cloud-AI dependence and the privacy-first local-transcription use case. Today's result resolves that contradiction cleanly:

> Users who want diarisation on transcripts already accept the cloud path via AssemblyAI. AI refinement features built on top of those transcripts inherit the same trade-off without compounding the privacy cost.

The spec can therefore come off hold with that framing as part of its design, if Ian chooses. *(This is a strategic decision separate from this investigation — flagged here because it directly follows from the conclusion above.)*

---

## 9. What's preserved

- This investigation log.
- The test plan at `Roadmap/Voice_ID_Segmentation_Test_Plan_2026-04-27.md` — kept for reference. It remains a sound test plan; the only thing the test produced was a negative answer.
- The 27 April test corpus (Tony + Chris recordings at short, medium, long durations) — useful for any future re-investigation if a new architecture warrants one.

The isolated test virtual environment under `C:\Ian\Python\Voice_ID_Test\` can be removed once any final notes have been transcribed from it. Nothing in DocAnalyser's production environment was modified during the investigation.

---

## 10. When to re-open

This investigation should be re-opened only if:

1. A genuinely new architectural approach emerges (e.g. a small CPU-runnable model with materially better same-speaker consistency than CAM++ or eres2net), **or**
2. The hardware envelope assumption changes — e.g. consumer NPUs become ubiquitous enough that DocAnalyser can rely on them, **or**
3. AssemblyAI becomes unavailable, prohibitively priced, or otherwise unusable.

Absent one of these triggers, no further investigation is warranted; the negative result holds.

---

*Investigation conducted by Ian Lucas, log compiled by Claude, 1 May 2026.*
