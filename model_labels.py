"""
model_labels.py
===============
Display-label helpers for AI model dropdowns.

The app stores and uses raw model IDs internally (e.g. "claude-opus-4-7"),
but displays labelled versions in dropdowns (e.g.
"claude-opus-4-7 — most capable"). These helpers convert between the two
forms so that the UI is friendly without breaking API calls or persisted
config values.

Tier data lives in model_info.json under
    [provider]["models"][model_id]["tier"]
and must be one of "premium", "balanced", or "fast". Models without a tier
(or with an unrecognised tier value) are displayed as their raw model ID —
no suffix — so this is safe to apply uniformly, including to providers
like Ollama that have no tier metadata at all.

Keep the separator (LABEL_SEPARATOR) consistent: model_id_from_label()
depends on its exact string to strip labels back to IDs correctly.
"""

from typing import List, Dict


# Human-readable suffix for each tier, keyed on model_info.json's "tier" values.
# These strings appear verbatim in the dropdown, so they're the user-facing
# names of the three tiers.
TIER_DISPLAY = {
    "premium":  "most capable",
    "balanced": "balanced",
    "fast":     "fast & cheap",
}

# Visual separator between the raw model ID and the tier suffix.
# Uses an em-dash flanked by single spaces. Change here to change everywhere.
LABEL_SEPARATOR = " — "


def label_from_model_id(model_id: str, provider: str, model_info: Dict) -> str:
    """
    Build a dropdown display label for a model.

    Example:
        label_from_model_id("claude-opus-4-7", "Anthropic (Claude)", info)
        -> "claude-opus-4-7 — most capable"

    Returns the raw model_id unchanged if:
      - model_id is empty or None
      - the provider isn't in model_info
      - the model_id isn't in model_info[provider]["models"]
      - the model has no "tier" field or an unrecognised tier value

    This graceful fallback means the helper is safe to call for any provider
    (including Ollama, which has no tier data) and for any model (including
    placeholder strings like "(Run Local AI Setup to download models)").
    """
    if not model_id:
        return model_id
    provider_data = model_info.get(provider) or {}
    models = provider_data.get("models") or {}
    entry = models.get(model_id) or {}
    tier = entry.get("tier")
    suffix = TIER_DISPLAY.get(tier)
    if suffix is None:
        return model_id
    return f"{model_id}{LABEL_SEPARATOR}{suffix}"


def model_id_from_label(label: str) -> str:
    """
    Strip the tier suffix from a dropdown label to recover the raw model ID.

    Example:
        model_id_from_label("claude-opus-4-7 — most capable")
        -> "claude-opus-4-7"

    Safe to call on:
      - Raw IDs (no separator present): returned unchanged
      - Empty strings: returned unchanged
      - None: returned as empty string

    This means every caller can safely route through this helper without
    first checking whether the value is already a raw ID.
    """
    if not label:
        return ""
    idx = label.find(LABEL_SEPARATOR)
    if idx < 0:
        return label
    return label[:idx]


def labels_from_model_ids(model_ids: List[str], provider: str, model_info: Dict) -> List[str]:
    """
    Bulk-convert a list of model IDs to labelled display strings, preserving
    order. Used to populate dropdown 'values' lists.
    """
    return [label_from_model_id(mid, provider, model_info) for mid in model_ids]
