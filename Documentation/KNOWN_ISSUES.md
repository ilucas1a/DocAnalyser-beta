# DocAnalyser — Known Issues & Technical Debt

A running log of bugs, architectural cleanups, and deferred enhancements
that have been identified but not yet acted on. Keep entries short, dated,
and actionable. When an item is fixed, either delete it and add a one-line
note in the relevant ProjectMap page's changelog section, or move it into
the **Fixed** section at the bottom with a resolution date.

---

## Bugs (non-critical)

*None currently.*

---

## Technical debt

### Model labels stored in document metadata instead of raw IDs
**Logged:** 2026-04-21  
**Severity:** Low — cosmetic / record-keeping, not functional  
**Scope:** `thread_viewer.py` (~4 metadata-save sites)

**Description.** After the `model_labels.py` wiring, `self.model_var`
(bound to the main-UI AI Model dropdown) holds the display label — e.g.
`"claude-opus-4-7 — most capable"` — rather than the raw model ID
(`"claude-opus-4-7"`).

API calls are now fine: `ai_handler.call_ai_provider()` translates labels
to raw IDs centrally (fix applied 2026-04-21). But several places in
`thread_viewer.py` read `self.model_var.get()` directly when saving
document metadata, so newly-saved thread/document records get labels
stored where raw IDs would historically have lived.

**Impact.** Minor:
- Human-readable for anyone poking at the database, so not harmful.
- Inconsistent with older records (pre-wiring) that hold raw IDs.
- Inconsistent with `subscription_manager._run_ai_and_save()`, which
  reads directly from config and correctly stores raw IDs.
- Downstream consumers that compare metadata model values to model IDs
  (e.g. analytics, digest cost calculations) may behave unexpectedly.

**Call sites to fix** (in `thread_viewer.py`):
- `_delete_current_exchange()` — thread metadata save
- `_handle_followup_result()` — thread metadata save after AI response
- `_save_edits_to_thread()` — two separate metadata saves

**Proposed fix (option A, recommended).** Add a small helper on
`ThreadViewerWindow`:

```python
def _raw_model_id(self) -> str:
    """Return the current model_var value as a raw model ID."""
    try:
        from model_labels import model_id_from_label
        return model_id_from_label(self.model_var.get()) or self.model_var.get()
    except Exception:
        return self.model_var.get()
```

Then replace `"model": self.model_var.get()` with `"model": self._raw_model_id()`
at the four call sites above.

**Proposed fix (option B).** Accept labels in metadata going forward.
Cheaper but leaves an inconsistency that future maintainers will have
to reason about. Not recommended.

**Related.** The 2026-04-21 central translator in `call_ai_provider()`
solved the API-call symptom of the same root cause. This issue is strictly
about *persisted* metadata.

---

## Deferred enhancements

### Ollama silent context-window truncation (`num_ctx` not set)
**Logged:** 2026-04-24  
**Severity:** High — local AI is effectively unusable for real workloads until fixed  
**Scope:** `ai_handler.py` — `_call_ollama()`

**Description.** The `_call_ollama()` call does not set `num_ctx` in the
request options. Ollama's server-side default is **2048 tokens**
(roughly 1,500 words) regardless of how large a context window the
underlying model actually supports. Modern local models typically
support 8K–128K tokens (Llama 3.1: 128K; Gemma 3: 128K; Qwen 2.5:
128K), but Ollama uses 2048 by default unless the client explicitly
asks for more.

**Impact.** Any Ollama call with meaningful input silently truncates
before the model sees the full content. The user sees a response but
has no way of knowing the model only saw the first ~1,500 words.

**Practical consequences.**
- Single-transcript summaries beyond ~1,500 words are silently
  incomplete.
- Subscription summaries (typically 800–2,000 words per source) often
  lose the tail end of each item.
- Digests combining multiple sources can't fit into 2K at all.
- Chunk-size settings (tiny/small/medium/large = 6K/12K/24K/52K chars)
  are nominally enforced by the chunking layer but hit the Ollama
  2K-token wall long before they should.

**Proposed fix (staged).**

1. *Minimum viable with hardware awareness.* Add `options={"num_ctx": N}`
   to the Ollama `client.chat.completions.create()` call, where `N` is
   chosen based on the user's available RAM and the selected model's
   size. Detect RAM via `psutil.virtual_memory().total`. Recommended
   mapping (7B model baseline; adjust for 13B ×1.7, 70B ×5):

   | User RAM | Recommended `num_ctx` | Maximum allowed |
   |----------|-----------------------|-----------------|
   | 8 GB     | 4K                    | 8K (with warning) |
   | 16 GB    | 8K                    | 16K             |
   | 32 GB    | 16K                   | 32K             |
   | 64 GB+   | 16K                   | 32K+ (model-dep) |

   This unblocks most realistic uses on most hardware without risking
   swap-thrash or out-of-memory on low-RAM machines.

2. *Per-model context awareness.* Read each model's actual max context
   from Ollama metadata (`ollama show <model>` exposes this) and cap
   `num_ctx` at `min(recommended, model_max)`. Prevents requesting a
   128K window on a 4K-window model.

3. *User-controlled override in Ollama settings UI.* Surface
   context-window size with plain-English labels tied to the user's
   hardware:
   - "Safe (recommended for your system)"
   - "Recommended (for typical documents)"
   - "Experimental — may slow your system or fail"
   - "Not recommended for your hardware"

   User can override the recommendation, but has to acknowledge a
   warning dialog that explains the trade-off. For combinations
   clearly unsafe (e.g. 8 GB RAM + 32K context + 13B model), the
   option may be disabled rather than just warned about.

4. *First-run detection.* On first Ollama use, or via a "Detect my
   system" button in Ollama settings, probe hardware and pre-populate
   the recommended setting so the user doesn't face a blank choice.

**Trade-offs the user should understand.**

- **RAM cost.** Context memory scales roughly linearly with
  `num_ctx`. On a 7B model, going from 2K → 32K typically adds 6–10 GB
  of RAM. Users with 16 GB total RAM can't run a 7B model at 32K
  context comfortably. This is the main risk of a blanket high default.
- **Speed.** Larger `num_ctx` reduces generation speed per token
  (especially above 16K) because attention is quadratic in sequence
  length. Users may perceive this as "Ollama got slower." For typical
  DocAnalyser workloads (process a full document in one go) the
  throughput gain from avoiding chunking usually outweighs the per-token
  slowdown, but it's model- and hardware-dependent.
- **Model support.** Not every model actually handles its advertised
  context well. Practical quality often degrades above 32K even when
  the model accepts larger windows. Staying at 8K–16K is usually the
  sweet spot.

**Related.** A broader inconsistency: `_call_anthropic()` hardcodes
`max_tokens`, while `_call_openai()`, `_call_gemini()`, `_call_xai()`,
and `_call_deepseek()` don't set it at all (relying on per-provider
server defaults that vary). Worth unifying once Ollama is done.

---

### Anthropic calls need streaming mode to raise `max_tokens` above ~16K
**Logged:** 2026-04-24  
**Severity:** Medium — limits the usefulness of the Claude provider for
very long structured outputs  
**Scope:** `ai_handler.py` — `_create_anthropic_message()` and
`_call_anthropic()`

**Description.** The Anthropic Python SDK requires streaming mode
(`client.messages.stream(...)`) for any call whose worst-case generation
time could exceed 10 minutes. In practice this triggers whenever
`max_tokens` is set above approximately 16K–20K — the SDK raises:

    Streaming is required for operations that may take longer than 10
    minutes. See https://github.com/anthropics/anthropic-sdk-python
    #long-requests for more details

The current implementation uses the non-streaming `client.messages.create()`
wrapper, which is simpler but gated to short-output workloads.

**Impact.** Capping `max_tokens` at 16,384 (the current 2026-04-24 setting)
keeps subscription checks and typical digests working, but blocks use of
the full 32K–64K output headroom modern Claude models support. A very
large briefing (many sources with expanded detail sections) could still
be cut off, though far less frequently than at the old 8K cap.

**Proposed fix.** Convert `_create_anthropic_message()` to use streaming
mode (`client.messages.stream()` as a context manager, accumulating text
chunks as they arrive, optionally emitting status updates to the log
along the way). Benefits:

- Removes the 10-minute gate; `max_tokens` can go to 32K or 64K freely.
- User sees activity in the log during long digests (nothing visible
  today during a 4-minute consolidation call).
- Matches current Anthropic SDK best practice.

Risks / work items:

- All callers of `_create_anthropic_message()` would need to handle the
  different return shape (today it returns `response.content[0].text`;
  streaming returns an accumulated string after the context block).
- Token usage tracking needs to move from `response.usage` to the final
  message metadata available after streaming completes.
- Error handling is slightly different — streaming errors arrive
  mid-stream rather than as a single exception on the call.
- Roughly 40–60 lines of change, plus testing against all call sites
  (subscription checks, digests, single-document summaries, followups).

**Related.** The 2026-04-24 max_tokens bump (8K → 32K) triggered this
error immediately on the first real workload. Rolled back to 16K as an
immediate fix. Full streaming conversion would let us go back to 32K+
safely.

---

### Pre-flight token estimation and digest-size guardrails
**Logged:** 2026-04-24  
**Severity:** Medium — protects against silent or confusing failures on
large digests  
**Scope:** `subscription_manager.generate_digest()` and associated UI in
`subscription_dialog.py`

**Description.** There is currently no pre-flight estimation of how
much input/output the combined digest work will require before the
AI call is made. At realistic scales this is fine on Claude, which has
200K input / 32K output headroom after the 2026-04-24 fix. But
degenerate cases are unprotected:

- User selects 50+ subscriptions for a single digest. Combined input
  approaches Claude's 200K context window; combined output could
  exceed even the new 32K cap.
- User on Ollama (with eventual `num_ctx` fix in place) selects more
  than their configured window allows.
- User on a provider with a lower cap (OpenAI gpt-5-mini, DeepSeek,
  older Gemini) silently hits a limit they didn't know existed.

**Impact.** Silent failure mode: the AI call either rejects the input
with a cryptic error, or (worse) succeeds but truncates the response,
giving the user an apparently complete digest that is actually missing
the tail end. Both are bad user experience and erode trust in the
feature.

**Proposed fix.**

1. *Token estimation helper.* Add a utility that estimates token count
   from character length (industry rule of thumb: ~4 characters per
   token for English, safer to use ~3 for a headroom buffer). Apply
   to the combined digest input before the AI call.

2. *Pre-flight check in `generate_digest()`.* Before calling the AI:
   - Look up the current provider/model's input and output limits from
     a central registry (extend `config.PROVIDER_REGISTRY` to carry
     per-model context/output limits, or add a new `MODEL_LIMITS`
     mapping).
   - Estimate combined input tokens and expected output tokens.
   - If combined input is within 10% of the model's input limit,
     warn the user and offer to break the digest up.
   - If selected-subs count exceeds a sensible threshold (say 30)
     regardless of token count, warn that digest quality degrades
     with very large source sets.

3. *UX guardrail in Subscriptions dialog.* When the user ticks more
   than ~30 subscriptions and clicks Generate Digest, show a confirm
   dialog: "You've selected N subscriptions. For best quality,
   consider generating separate digests by folder. Continue anyway,
   or cancel and re-select?"

4. *Output-ceiling awareness.* If the briefing-format prompt is
   detected (by prompt name or heuristic), factor in that the output
   will be substantial — rough rule: expect output tokens ≈ input
   tokens for briefing format. Warn earlier than for plain-summary
   prompts.

**Why this matters beyond digests.** The same approach (token
estimation + pre-flight check + user-facing warning for borderline
cases) is worth applying to single-document AI calls too, especially
on Ollama where the `num_ctx` ceiling is much tighter. Once the
utility exists, reusing it across the app is cheap.

**Related.** Depends on completion of the Ollama `num_ctx` work
(entry above) to be fully coherent — Ollama's ceiling is set at call
time and the pre-flight check needs to read whatever value is in
effect.

---

### Centred paragraphs in Markdown-to-Word/PDF output
**Logged:** 2026-04-24  
**Severity:** Low — cosmetic only  
**Scope:** `thread_viewer_copy.py` — `_markdown_to_html_content()`

**Description.** Standard Markdown has no syntax for centring a
paragraph. The briefing-format prompt (and likely future prompts)
would benefit from the ability to centre specific lines — e.g. the
italicised subtitle *(click "Detail" to go to more information about
any point)* that sits directly under the Key Points heading. Asking
the AI to "centre" a line currently has no effect because
`_markdown_to_html_content` does not emit any centring CSS or
alignment attribute.

**Proposed fix.** Two options, in increasing order of generality:

1. *Support raw HTML centring in Markdown.* Allow the AI to emit
   `<div align="center">...</div>` or
   `<p style="text-align: center;">...</p>` inside the Markdown, and
   have `_markdown_to_html_content` pass this through to the HTML
   output unmolested rather than escaping the tags. Then update the
   briefing prompt to use this syntax where centring is wanted.
   Straightforward, but opens the door to the AI emitting arbitrary
   HTML, which may or may not be desirable depending on the renderer.

2. *Custom marker convention.* Define a marker such as
   `{{center}}...{{/center}}` or `^^^text^^^` that
   `_markdown_to_html_content` translates to centred HTML. Cleaner
   separation between content and rendering; keeps the AI away from
   raw HTML. More code, but more controlled.

**Scope of work.** Either option is small — roughly 10–20 lines in
`_markdown_to_html_content` plus a prompt update and a test pass to
confirm centring survives the HTML → clipboard → Word paste path.

**Related.** Sits alongside the broader Thread Viewer rendering
extensions — `{#anchor}` / `[text](#anchor)` internal links,
suppression of the prompt text in rendered Word output, and the
document heading using the generated title. Worth doing all of these
together in one focused pass over `_markdown_to_html_content`, rather
than chipping at them one by one.

---

## Fixed

*Log resolved items here with a resolution date, or move them into the
relevant ProjectMap page's module-level notes.*
