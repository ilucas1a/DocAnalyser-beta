"""
apply_model_labels_wiring.py
============================

Wires model_labels.py helpers into Main.py and settings_manager.py.

Run from the DocAnalyser project root (where Main.py lives):

    cd C:\\Ian\\Python\\GetTextFromYouTube\\DocAnalyzer_DEV
    python apply_model_labels_wiring.py

What it does
------------
* Creates Main.py.bak and settings_manager.py.bak (only if .bak doesn't already
  exist — won't overwrite an earlier backup).
* Applies 14 edits to Main.py and 5 edits to settings_manager.py, each defined
  as a (label, old, new) tuple. The previous session counted 13 Main.py edits
  by collapsing the two tail-end set sites; they're kept separate here so each
  failure (if any) is named individually.
* Idempotent: any edit whose `new` text is already present is reported as
  SKIPPED rather than re-applied. Safe to re-run after partial fixes.
* Atomic-ish: all edits applied in memory, ast.parse() validates the result,
  and only then are the files overwritten. If anything fails, the original
  files are untouched (the .bak from a previous successful run remains intact).
* Per-edit reporting: APPLIED / SKIPPED / FAILED with the label name so any
  miss is immediately actionable.

Design choices worth knowing
----------------------------
* settings_manager.py needs no new imports because it's a mixin — the helper
  trio (`_model_dropdown_values`, `_set_model_var`, `_model_id_from_var`) is
  added to the main App class in Main.py and is reachable from the mixin via
  `self.*`. So model_labels is imported only in Main.py.
* Where the same line appears in multiple sites (e.g. `self.model_var.set("")`
  twice in `on_provider_select`), the tuple uses Python's `str.replace` with
  no count, so all matching occurrences in that file are wrapped in one go.
* Where a line might collide with an unrelated occurrence elsewhere, the
  tuple includes a line of surrounding context to make the match unique.

Exit codes
----------
  0 = all edits applied or already-applied (success either way)
  1 = at least one edit's `old` text could not be located
  2 = post-patch ast.parse failed; nothing was written
"""

from __future__ import annotations

import ast
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
MAIN_PY = REPO / "Main.py"
SETTINGS_PY = REPO / "settings_manager.py"


# --------------------------------------------------------------------------- #
# Helper trio source — inserted into Main.py just before the existing
# _generate_model_description method. Indented for class-body placement.
# --------------------------------------------------------------------------- #

HELPER_TRIO = '''    def _model_dropdown_values(self, model_ids):
        """Convert raw model IDs to display labels for combo['values']."""
        provider = self.provider_var.get()
        return labels_from_model_ids(model_ids, provider, self.model_info)

    def _set_model_var(self, model_id):
        """Set self.model_var to the labelled form of the given raw model ID."""
        provider = self.provider_var.get()
        self.model_var.set(label_from_model_id(model_id, provider, self.model_info))

    def _model_id_from_var(self):
        """Return the raw model ID from self.model_var (which holds a label)."""
        return model_id_from_label(self.model_var.get())

'''


# --------------------------------------------------------------------------- #
# Main.py edits
# --------------------------------------------------------------------------- #

MAIN_EDITS = [

    # 1. Import the three helpers right after the subscription_dialog import.
    ("01 import: model_labels helpers",
     "from subscription_dialog import open_subscriptions_dialog\n",
     "from subscription_dialog import open_subscriptions_dialog\n"
     "from model_labels import (\n"
     "    label_from_model_id,\n"
     "    model_id_from_label,\n"
     "    labels_from_model_ids,\n"
     ")\n"),

    # 2. Cache self.model_info immediately after self.models is loaded so the
    #    label helpers can be used elsewhere in __init__ and beyond.
    #    _load_model_info() is an existing class method (returns {} on any error).
    ("02 cache: self.model_info from _load_model_info()",
     "        self.models = load_models()\n",
     "        self.models = load_models()\n"
     "        self.model_info = self._load_model_info()\n"),

    # 3. Wrap the initial value of self.model_var in label_from_model_id().
    #    default_provider and self.model_info are both already in scope here.
    ("03 wrap: self.model_var initial value",
     "        self.model_var = tk.StringVar(value=default_model)\n",
     "        self.model_var = tk.StringVar(\n"
     "            value=label_from_model_id(default_model, default_provider, self.model_info)\n"
     "        )\n"),

    # 4. Strip the label when reading the model into standalone metadata
    #    so the saved record contains the raw model ID, not the labelled form.
    ("04 strip: standalone metadata model",
     '                    "model": self.model_var.get(),\n',
     '                    "model": model_id_from_label(self.model_var.get()),\n'),

    # 5. Combo updates that pull from `updated_models[provider]`. This exact
    #    line appears in the auto-refresh path AND the curated-update path;
    #    str.replace with no count wraps both occurrences in one go.
    ("05 wrap combo: updated_models[provider]  (replace-all)",
     "                            combo['values'] = updated_models[provider]\n",
     "                            combo['values'] = self._model_dropdown_values(updated_models[provider])\n"),

    # 6. Combo updates that pull from `self.models.get("Ollama (Local)", [])`.
    #    Appears in: Local AI Setup callback, Local Model Manager callback,
    #    and the Ollama branch of on_provider_select. All three sites are
    #    wrapped by this single replace-all.
    ("06 wrap combo: Ollama models  (replace-all)",
     "                        combo['values'] = self.models.get(\"Ollama (Local)\", [])\n",
     "                        combo['values'] = self._model_dropdown_values(self.models.get(\"Ollama (Local)\", []))\n"),

    # 7. Combo update for the non-Ollama branch of on_provider_select.
    ("07 wrap combo: provider models (on_provider_select)",
     "            combo['values'] = self.models.get(provider, [])\n",
     "            combo['values'] = self._model_dropdown_values(self.models.get(provider, []))\n"),

    # 8. set(model_name) after Local AI Setup completes. Unique line.
    ("08 wrap set: model_name (Local AI Setup)",
     "                    self.model_var.set(model_name)\n",
     "                    self._set_model_var(model_name)\n"),

    # 9. set(preferred_model) — appears twice in on_provider_select
    #    (Ollama branch and non-Ollama branch). Replace-all.
    ("09 wrap set: preferred_model  (replace-all)",
     "                self.model_var.set(preferred_model)\n",
     "                self._set_model_var(preferred_model)\n"),

    # 10. set(available_models[0]) — Ollama fallback. Surrounding context
    #     ensures uniqueness even if the bare line were ever reused.
    ("10 wrap set: available_models[0] (Ollama fallback)",
     "            elif available_models and not available_models[0].startswith(\"(\"):\n"
     "                self.model_var.set(available_models[0])\n",
     "            elif available_models and not available_models[0].startswith(\"(\"):\n"
     "                self._set_model_var(available_models[0])\n"),

    # 11. set("") — appears twice in on_provider_select (Ollama "no models"
    #     and non-Ollama "no preferred"). Replace-all.
    ("11 wrap set: empty string  (replace-all)",
     "                self.model_var.set(\"\")\n",
     "                self._set_model_var(\"\")\n"),

    # 12. set(recommended_model) in _select_recommended_model. Surrounding
    #     context anchors uniquely on the in-membership guard.
    ("12 wrap set: recommended_model",
     "            if recommended_model in current_models:\n"
     "                self.model_var.set(recommended_model)\n",
     "            if recommended_model in current_models:\n"
     "                self._set_model_var(recommended_model)\n"),

    # 13. set(user_default) in _select_default_or_recommended_model. Anchored
    #     on its own in-membership guard.
    ("13 wrap set: user_default",
     "        if user_default and user_default in current_models:\n"
     "            self.model_var.set(user_default)\n",
     "        if user_default and user_default in current_models:\n"
     "            self._set_model_var(user_default)\n"),

    # 14. Insert the helper trio immediately before _generate_model_description.
    ("14 insert: helper trio (before _generate_model_description)",
     "    def _generate_model_description(self, model_id, provider):\n",
     HELPER_TRIO + "    def _generate_model_description(self, model_id, provider):\n"),
]


# --------------------------------------------------------------------------- #
# settings_manager.py edits
# --------------------------------------------------------------------------- #
#
# Strategy: settings_manager.py is a mixin into the main App class, so it
# reaches the helper trio via `self.*` and needs no new imports. The three
# `model = self.model_var.get()` strip sites and the two block sites
# (on_provider_select_in_settings and the Ollama-test refresh) cover all
# the wiring needed there.
# --------------------------------------------------------------------------- #

SETTINGS_EDITS = [

    # S1. set_default_model() nested function: strip label before saving.
    #     Anchored on the def + provider pair to disambiguate from the other
    #     two `model = self.model_var.get()` sites.
    ("S1 strip: set_default_model() get",
     "        def set_default_model():\n"
     "            provider = self.provider_var.get()\n"
     "            model = self.model_var.get()\n",
     "        def set_default_model():\n"
     "            provider = self.provider_var.get()\n"
     "            model = self._model_id_from_var()\n"),

    # S2. save() nested function inside open_ai_settings: strip label before
    #     persisting last_model. Anchored on the surrounding pattern.
    ("S2 strip: save() get",
     "            provider = self.provider_var.get()\n"
     "            model = self.model_var.get()\n"
     "            if provider and model:\n"
     "                if \"last_model\" not in self.config:\n",
     "            provider = self.provider_var.get()\n"
     "            model = self._model_id_from_var()\n"
     "            if provider and model:\n"
     "                if \"last_model\" not in self.config:\n"),

    # S3. on_provider_select_in_settings: combo update + 4 set calls. Done
    #     as one block so the structural shape of the if/else stays obvious.
    ("S3 block: on_provider_select_in_settings (combo + 4 sets)",
     "        self.model_combo['values'] = self.models.get(provider, [])\n"
     "        last_model = self.config[\"last_model\"].get(provider, \"\")\n"
     "        if last_model in self.models.get(provider, []):\n"
     "            self.model_var.set(last_model)\n"
     "        else:\n"
     "            # For Ollama, select the first available model if any\n"
     "            if provider == \"Ollama (Local)\" and self.models.get(provider):\n"
     "                models_list = self.models.get(provider, [])\n"
     "                # Skip placeholder entries\n"
     "                real_models = [m for m in models_list if not m.startswith(\"(\")]\n"
     "                if real_models:\n"
     "                    self.model_var.set(real_models[0])\n"
     "                else:\n"
     "                    self.model_var.set(\"\")\n"
     "            else:\n"
     "                self.model_var.set(\"\")\n",
     "        self.model_combo['values'] = self._model_dropdown_values(self.models.get(provider, []))\n"
     "        last_model = self.config[\"last_model\"].get(provider, \"\")\n"
     "        if last_model in self.models.get(provider, []):\n"
     "            self._set_model_var(last_model)\n"
     "        else:\n"
     "            # For Ollama, select the first available model if any\n"
     "            if provider == \"Ollama (Local)\" and self.models.get(provider):\n"
     "                models_list = self.models.get(provider, [])\n"
     "                # Skip placeholder entries\n"
     "                real_models = [m for m in models_list if not m.startswith(\"(\")]\n"
     "                if real_models:\n"
     "                    self._set_model_var(real_models[0])\n"
     "                else:\n"
     "                    self._set_model_var(\"\")\n"
     "            else:\n"
     "                self._set_model_var(\"\")\n"),

    # S4. Ollama "Test connection" success path: refresh the dropdown.
    ("S4 block: Ollama test connection (combo + set)",
     "                # If Ollama is currently selected, refresh the model dropdown\n"
     "                if self.provider_var.get() == \"Ollama (Local)\":\n"
     "                    self.model_combo['values'] = models\n"
     "                    if models:\n"
     "                        self.model_var.set(models[0])\n",
     "                # If Ollama is currently selected, refresh the model dropdown\n"
     "                if self.provider_var.get() == \"Ollama (Local)\":\n"
     "                    self.model_combo['values'] = self._model_dropdown_values(models)\n"
     "                    if models:\n"
     "                        self._set_model_var(models[0])\n"),

    # S5. save_model_selection(): strip label before saving last_model.
    #     Anchored on the docstring + provider pair.
    ("S5 strip: save_model_selection() get",
     "    def save_model_selection(self):\n"
     "        \"\"\"Save the selected model for the current provider\"\"\"\n"
     "        provider = self.provider_var.get()\n"
     "        model = self.model_var.get()\n",
     "    def save_model_selection(self):\n"
     "        \"\"\"Save the selected model for the current provider\"\"\"\n"
     "        provider = self.provider_var.get()\n"
     "        model = self._model_id_from_var()\n"),
]


# --------------------------------------------------------------------------- #
# Engine
# --------------------------------------------------------------------------- #

def apply_edits(text: str, edits: list[tuple[str, str, str]]) -> tuple[str, list, list, list]:
    """Apply (label, old, new) tuples to `text`. Returns (new_text, applied,
    skipped, failed).

    Idempotency rule: an edit is SKIPPED whenever `new` is already present in
    the text. This is the right check even for prepend/append edits where
    `old` is a substring of `new` (e.g. the import block, the cache line,
    the helper-trio insertion) — once the new form is in the file, the work
    is done and re-applying would duplicate it.

    For replace-all edits, after first application `old` is gone and `new`
    is present, so the same rule still skips correctly."""
    applied, skipped, failed = [], [], []
    for label, old, new in edits:
        if new in text:
            # Already applied — leave alone
            skipped.append(label)
            continue
        if old not in text:
            failed.append(label)
            continue
        text = text.replace(old, new)
        applied.append(label)
    return text, applied, skipped, failed


def report(file_label: str, applied: list, skipped: list, failed: list) -> None:
    print(f"\n=== {file_label} ===")
    if not (applied or skipped or failed):
        print("  (no edits configured)")
        return
    for label in applied:
        print(f"  [APPLIED] {label}")
    for label in skipped:
        print(f"  [SKIPPED] {label}  (new text already present)")
    for label in failed:
        print(f"  [FAILED ] {label}  (old text not found)")


def backup_once(src: Path) -> Path:
    """Copy src -> src.bak unless the .bak already exists."""
    bak = src.with_suffix(src.suffix + ".bak")
    if bak.exists():
        print(f"  backup exists, leaving untouched: {bak.name}")
    else:
        shutil.copy2(src, bak)
        print(f"  backup created: {bak.name}")
    return bak


def main() -> int:
    # --- pre-flight ---------------------------------------------------------
    for p in (MAIN_PY, SETTINGS_PY):
        if not p.exists():
            print(f"ERROR: {p.name} not found at {p}")
            return 1
        if not p.is_file():
            print(f"ERROR: {p.name} is not a regular file")
            return 1

    print("Backing up source files...")
    backup_once(MAIN_PY)
    backup_once(SETTINGS_PY)

    # --- apply in memory ----------------------------------------------------
    main_src_orig = MAIN_PY.read_text(encoding="utf-8")
    settings_src_orig = SETTINGS_PY.read_text(encoding="utf-8")

    main_src_new, m_applied, m_skipped, m_failed = apply_edits(main_src_orig, MAIN_EDITS)
    settings_src_new, s_applied, s_skipped, s_failed = apply_edits(settings_src_orig, SETTINGS_EDITS)

    report("Main.py", m_applied, m_skipped, m_failed)
    report("settings_manager.py", s_applied, s_skipped, s_failed)

    # --- abort on any FAILED edit ------------------------------------------
    if m_failed or s_failed:
        print("\nABORT: one or more edits failed to find their `old` text.")
        print("Files left unchanged. Backups untouched.")
        print("Investigate the FAILED labels above; the `old` strings in this")
        print("script may need to be adjusted for your current file content.")
        return 1

    # --- syntax-validate the patched sources -------------------------------
    print("\nValidating Python syntax of patched sources...")
    for name, src in (("Main.py", main_src_new), ("settings_manager.py", settings_src_new)):
        try:
            ast.parse(src)
            print(f"  {name}: syntax OK")
        except SyntaxError as e:
            print(f"  {name}: SYNTAX ERROR  line {e.lineno}: {e.msg}")
            print("\nABORT: patched source would not parse. Files NOT written.")
            print("Backups remain intact. Restore with:")
            print("  copy Main.py.bak Main.py")
            print("  copy settings_manager.py.bak settings_manager.py")
            return 2

    # --- nothing changed? short-circuit -------------------------------------
    if main_src_new == main_src_orig and settings_src_new == settings_src_orig:
        print("\nNothing to do — both files were already fully wired.")
        return 0

    # --- write -------------------------------------------------------------
    if main_src_new != main_src_orig:
        MAIN_PY.write_text(main_src_new, encoding="utf-8")
        print(f"\nWrote: {MAIN_PY.name}")
    if settings_src_new != settings_src_orig:
        SETTINGS_PY.write_text(settings_src_new, encoding="utf-8")
        print(f"Wrote: {SETTINGS_PY.name}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
