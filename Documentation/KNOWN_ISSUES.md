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

*None currently.*

---

## Fixed

*Log resolved items here with a resolution date, or move them into the
relevant ProjectMap page's module-level notes.*
