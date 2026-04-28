"""
corrections_db_adapter.py — Domain API for Corrections Lists (v1.7-alpha)

Bridges between higher-level callers (cleanup dialog, settings UI,
"Add to Corrections List" buttons) and the db_manager primitives.

Provides:
  * Cleaner method names (list_create vs db_create_corrections_list)
  * JSON export/import using the same schema as default_corrections.json
  * Bundled-list protection — the seeded "General" list cannot be
    renamed or deleted accidentally; users wanting to customise it
    are pointed to list_duplicate() instead.

This module is the API surface that Day 5+ UI code should call.
Day 5 wires apply_corrections_to_text() into transcript_cleaner.py
Phase 3; Days 6-8 build the management/Add-to-list dialogs on top
of the CRUD methods here.

Author: DocAnalyser Development Team
Date: 28 April 2026 (v1.7-alpha Day 2)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional, List

import db_manager as db


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Name of the bundled list that ships with DocAnalyser. Reserved.
BUNDLED_LIST_NAME = "General"

# Schema version written into exported JSON files. Bump if format changes.
EXPORT_SCHEMA_VERSION = "1.7.0a1"


# ---------------------------------------------------------------------------
# Lists — CRUD
# ---------------------------------------------------------------------------

def list_get_all(workspace_id: Optional[int] = None) -> List[dict]:
    """Return all corrections lists in the given workspace
    (or workspace_id IS NULL by default)."""
    return db.db_get_all_corrections_lists(workspace_id=workspace_id)


def list_get(list_id: int) -> Optional[dict]:
    """Return a single list by id."""
    return db.db_get_corrections_list(list_id)


def list_get_by_name(name: str,
                     workspace_id: Optional[int] = None) -> Optional[dict]:
    """Return a list by name (within optional workspace), or None."""
    return db.db_get_corrections_list_by_name(name, workspace_id=workspace_id)


def list_create(name: str, description: Optional[str] = None,
                workspace_id: Optional[int] = None) -> int:
    """
    Create a new list. Returns the new list_id.

    Raises ValueError if:
      * the name is empty or whitespace-only
      * a list with the same name already exists in the same workspace
    """
    if not name or not name.strip():
        raise ValueError("List name cannot be empty.")
    name = name.strip()
    existing = db.db_get_corrections_list_by_name(name, workspace_id=workspace_id)
    if existing is not None:
        raise ValueError(f"A list named {name!r} already exists.")
    return db.db_create_corrections_list(
        name=name, description=description, workspace_id=workspace_id
    )


def list_update(list_id: int, **fields) -> bool:
    """
    Update list metadata. Allowed: name, description.

    Renaming the bundled "General" list is blocked (raises ValueError).
    Renaming to a name already used by another list in the same workspace
    is also blocked.
    """
    current = db.db_get_corrections_list(list_id)
    if current is None:
        return False

    if "name" in fields:
        new_name = (fields["name"] or "").strip()
        if not new_name:
            raise ValueError("List name cannot be empty.")
        # Block renaming the bundled list
        if (current["name"] == BUNDLED_LIST_NAME
                and new_name != BUNDLED_LIST_NAME):
            raise ValueError(
                f"The bundled {BUNDLED_LIST_NAME!r} list cannot be renamed. "
                f"Use list_duplicate() if you want a customised version."
            )
        # Uniqueness check
        clash = db.db_get_corrections_list_by_name(
            new_name, workspace_id=current.get("workspace_id")
        )
        if clash and clash["id"] != list_id:
            raise ValueError(f"A list named {new_name!r} already exists.")
        fields["name"] = new_name

    return db.db_update_corrections_list(list_id, **fields)


def list_delete(list_id: int) -> bool:
    """
    Delete a list and all its corrections.

    Deleting the bundled "General" list is blocked (raises ValueError).
    Returns True if a row was deleted, False if no row matched.
    """
    current = db.db_get_corrections_list(list_id)
    if current is None:
        return False
    if current["name"] == BUNDLED_LIST_NAME:
        raise ValueError(
            f"The bundled {BUNDLED_LIST_NAME!r} list cannot be deleted. "
            f"Edit its contents or duplicate it instead."
        )
    return db.db_delete_corrections_list(list_id)


def list_duplicate(list_id: int, new_name: str) -> int:
    """
    Duplicate a list (metadata + all corrections) under a new name.
    Returns the new list_id.

    The intended use case is letting users start from "General" and
    customise without touching the bundled list.
    """
    src = db.db_get_corrections_list(list_id)
    if src is None:
        raise ValueError(f"List id {list_id} not found.")
    new_id = list_create(
        name=new_name,
        description=src.get("description"),
        workspace_id=src.get("workspace_id"),
    )
    for entry in db.db_get_corrections(list_id):
        db.db_add_correction(
            list_id=new_id,
            original_text=entry["original_text"],
            corrected_text=entry["corrected_text"],
            case_sensitive=entry["case_sensitive"],
            word_boundary=entry["word_boundary"],
            notes=entry.get("notes"),
        )
    logging.info(
        "Duplicated list %r (id=%d) -> %r (id=%d)",
        src["name"], list_id, new_name, new_id
    )
    return new_id


# ---------------------------------------------------------------------------
# Corrections — CRUD
# ---------------------------------------------------------------------------

def correction_get_all_for_list(list_id: int) -> List[dict]:
    """Return all entries in a list, in insertion order."""
    return db.db_get_corrections(list_id)


def correction_get(correction_id: int) -> Optional[dict]:
    """Return a single entry by id, or None."""
    return db.db_get_correction(correction_id)


def correction_add(list_id: int, original_text: str, corrected_text: str,
                   case_sensitive: bool = False, word_boundary: bool = True,
                   notes: Optional[str] = None) -> int:
    """
    Add a correction entry to a list. Returns the new correction id.

    corrected_text may be empty (deletes the matched text on apply).
    original_text must be non-empty.
    """
    if not original_text:
        raise ValueError("original_text cannot be empty.")
    return db.db_add_correction(
        list_id=list_id,
        original_text=original_text,
        corrected_text=corrected_text,
        case_sensitive=case_sensitive,
        word_boundary=word_boundary,
        notes=notes,
    )


def correction_update(correction_id: int, **fields) -> bool:
    """
    Update an entry. Allowed: original_text, corrected_text,
    case_sensitive, word_boundary, notes.
    """
    if "original_text" in fields and not fields["original_text"]:
        raise ValueError("original_text cannot be empty.")
    return db.db_update_correction(correction_id, **fields)


def correction_delete(correction_id: int) -> bool:
    """Delete an entry."""
    return db.db_delete_correction(correction_id)


# ---------------------------------------------------------------------------
# JSON Export / Import
# ---------------------------------------------------------------------------

def list_export_json(list_id: int, file_path: str) -> bool:
    """
    Export a list and its entries to a JSON file in the same format as
    default_corrections.json. Returns True on success.
    """
    lst = db.db_get_corrections_list(list_id)
    if lst is None:
        raise ValueError(f"List id {list_id} not found.")
    entries = db.db_get_corrections(list_id)
    payload = {
        "name": lst["name"],
        "version": EXPORT_SCHEMA_VERSION,
        "description": lst.get("description") or "",
        "entries": [
            {
                "original": e["original_text"],
                "corrected": e["corrected_text"],
                "case_sensitive": bool(e["case_sensitive"]),
                "word_boundary": bool(e["word_boundary"]),
                "notes": e.get("notes") or "",
            }
            for e in entries
        ],
    }
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    logging.info(
        "Exported %d corrections from list %r to %s",
        len(entries), lst["name"], file_path
    )
    return True


def list_import_json(file_path: str,
                     name_override: Optional[str] = None,
                     workspace_id: Optional[int] = None) -> int:
    """
    Import a JSON file as a NEW corrections list.

    file_path:        Path to a JSON file in default_corrections.json format.
    name_override:    If provided, use this as the new list name (otherwise
                      use the 'name' field from the JSON file).
    workspace_id:     Workspace to attach the new list to. None for v1.7-alpha.

    If a list with the resolved name already exists, the imported name has
    " (imported)" appended; if that's also taken, " (imported 2)", and so on.

    Returns the new list_id.
    """
    if not os.path.exists(file_path):
        raise ValueError(f"File not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    raw_name = (name_override or data.get("name") or "Imported list").strip()
    description = data.get("description", "")
    entries = data.get("entries", [])

    # Resolve name conflicts by appending " (imported N)"
    resolved_name = raw_name
    suffix = 0
    while db.db_get_corrections_list_by_name(
            resolved_name, workspace_id=workspace_id) is not None:
        suffix += 1
        if suffix == 1:
            resolved_name = f"{raw_name} (imported)"
        else:
            resolved_name = f"{raw_name} (imported {suffix})"

    new_id = db.db_create_corrections_list(
        name=resolved_name,
        description=description,
        workspace_id=workspace_id,
    )
    for entry in entries:
        original = entry.get("original", "")
        if not original:
            continue
        db.db_add_correction(
            list_id=new_id,
            original_text=original,
            corrected_text=entry.get("corrected", ""),
            case_sensitive=bool(entry.get("case_sensitive", False)),
            word_boundary=bool(entry.get("word_boundary", True)),
            notes=entry.get("notes"),
        )
    logging.info(
        "Imported %d corrections into list %r (id=%d) from %s",
        len(entries), resolved_name, new_id, file_path
    )
    return new_id
