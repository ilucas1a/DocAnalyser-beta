"""
backups_manager.py — Domain API for Document Backups (v1.7-alpha Day 7)

Bridges between higher-level callers (transcript cleanup dialog,
Source Document panel "Restore backup" button, Backups dialog) and
the db_manager primitives.

Owns the on-disk payload schema for the `content_blob` column in the
backups table. Callers pass in plain Python dicts and lists; this
module handles JSON serialisation and deserialisation, payload
versioning, and the pruning policy (10 most-recent per document).

Trigger types in v1.7-alpha:
  * "cleanup_open"      — auto-fired when the cleanup dialog opens
  * "pre_restore"       — auto-fired before restore_backup() swaps in
                          older content (counter-backup safety net)
  * "manual"            — reserved for future "Create backup" buttons

Future v1.7-full triggers (added by appending here, no schema change):
  * "ai_refinement", "session_start", "import" …

Payload schema (content_blob, JSON-encoded):
  {
    "version": 1,
    "entries": [...],            # the document's entries list
    "metadata_subset": {...}     # caller-curated dict of metadata
                                 # fields that cleanup can mutate
  }

Author: DocAnalyser Development Team
Date: 30 April 2026 (v1.7-alpha Day 7)
"""

from __future__ import annotations

import json
import logging
from typing import Optional, List, Dict, Any

import db_manager as db


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum number of backups retained per document. Older backups beyond
# this count are pruned automatically after every create_backup() call.
MAX_BACKUPS_PER_DOCUMENT = 10

# Payload schema version. Bump if the dict shape inside content_blob
# changes in a non-backward-compatible way.
PAYLOAD_VERSION = 1

# Recognised trigger_type values for v1.7-alpha. Not enforced at the DB
# layer (column is free-text), but documented here so callers stay
# consistent. v1.7-full will append more entries.
TRIGGER_CLEANUP_OPEN = "cleanup_open"
TRIGGER_PRE_RESTORE = "pre_restore"
TRIGGER_MANUAL = "manual"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialise_payload(entries: List[Dict[str, Any]],
                       metadata_subset: Optional[Dict[str, Any]] = None) -> str:
    """
    Build the JSON-encoded content_blob from an entries list and an
    optional metadata-subset dict. Always stamps the current
    PAYLOAD_VERSION so future loaders can branch on it.
    """
    payload = {
        "version": PAYLOAD_VERSION,
        "entries": entries or [],
        "metadata_subset": metadata_subset or {},
    }
    return json.dumps(payload, ensure_ascii=False)


def _deserialise_payload(content_blob: str) -> Dict[str, Any]:
    """
    Parse a content_blob back to a dict. Returns a dict with the
    canonical shape regardless of the stored version, so callers
    don't have to handle missing keys.

    Raises ValueError if the blob is unparseable — callers should
    treat that as a corrupted backup and surface it to the user
    rather than silently substituting an empty payload.
    """
    try:
        data = json.loads(content_blob)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Backup payload is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("Backup payload is not a JSON object")

    return {
        "version": data.get("version", 1),
        "entries": data.get("entries", []),
        "metadata_subset": data.get("metadata_subset", {}),
    }


# ---------------------------------------------------------------------------
# Public API — create
# ---------------------------------------------------------------------------

def create_backup(document_id: str,
                  trigger_type: str,
                  entries: List[Dict[str, Any]],
                  metadata_subset: Optional[Dict[str, Any]] = None,
                  label: Optional[str] = None) -> int:
    """
    Take a snapshot of a document's current entries and return the new
    backup id. Automatically prunes the document's backups down to the
    MAX_BACKUPS_PER_DOCUMENT most-recent rows after the insert.

    Args:
        document_id:     The document this backup belongs to.
        trigger_type:    One of the TRIGGER_* constants, or any short
                         lowercase string for future trigger kinds.
        entries:         The entries list to snapshot.
        metadata_subset: Optional dict of metadata fields to include
                         in the snapshot. Pass only the fields that
                         can be mutated by whatever operation is about
                         to happen (e.g. cleanup may rewrite speaker
                         names, so include word_speaker_names).
        label:           Optional short user-facing label. None is fine
                         for auto-triggered backups; a human-typed
                         label fits manual backups.

    Returns:
        The new backup id (use it to load the backup later via
        get_backup, or to identify it in the dialog).
    """
    blob = _serialise_payload(entries, metadata_subset)

    backup_id = db.db_create_backup(
        document_id=document_id,
        trigger_type=trigger_type,
        content_blob=blob,
        label=label,
    )

    # Retention pruning. Run unconditionally — cheap when there's
    # nothing to prune, essential when there is.
    pruned = db.db_prune_backups(document_id, keep=MAX_BACKUPS_PER_DOCUMENT)
    if pruned:
        logging.info(
            "backups_manager: created backup %s for doc %s (%s); "
            "pruned %d older backup(s).",
            backup_id, document_id, trigger_type, pruned
        )
    else:
        logging.debug(
            "backups_manager: created backup %s for doc %s (%s).",
            backup_id, document_id, trigger_type
        )

    return backup_id


# ---------------------------------------------------------------------------
# Public API — list / get
# ---------------------------------------------------------------------------

def list_backups(document_id: str) -> List[Dict[str, Any]]:
    """
    Return all backups for a document, newest first.
    Each row includes id, document_id, trigger_type, label, created_at
    but NOT content_blob (use get_backup for that).
    """
    return db.db_list_backups(document_id)


def get_backup(backup_id: int) -> Optional[Dict[str, Any]]:
    """
    Load a single backup by id, with its content_blob deserialised
    into a 'payload' dict (keys: version, entries, metadata_subset).

    Returns None if the backup row doesn't exist.
    Raises ValueError if the row exists but its payload is corrupted —
    callers should surface that to the user rather than swallowing it.
    """
    row = db.db_get_backup(backup_id)
    if row is None:
        return None

    blob = row.get("content_blob") or ""
    row["payload"] = _deserialise_payload(blob)
    # Drop the raw blob from the returned dict — callers should use
    # 'payload' instead. Saves a noisy duplicate in the UI layer.
    row.pop("content_blob", None)
    return row


# ---------------------------------------------------------------------------
# Public API — restore / delete
# ---------------------------------------------------------------------------

def restore_backup(backup_id: int,
                   current_entries: List[Dict[str, Any]],
                   current_metadata_subset: Optional[Dict[str, Any]] = None
                   ) -> Dict[str, Any]:
    """
    Restore a backup. Before swapping the entries in, automatically
    create a counter-backup of the *current* state with trigger_type
    "pre_restore" so a misclick is itself recoverable.

    The counter-backup goes through the same pruning rules — if a
    document is already at the cap, the oldest will be displaced to
    make room.

    Args:
        backup_id:                The backup to restore from.
        current_entries:          The document's current entries
                                  (snapshotted into the counter-backup).
        current_metadata_subset:  The matching metadata subset for the
                                  counter-backup. Should be the same
                                  shape the original backup used.

    Returns:
        A dict with keys:
          'restored_payload'    — the deserialised payload to load
                                  back into the document
          'counter_backup_id'   — id of the just-created counter-backup,
                                  in case the UI wants to surface it

    Raises:
        ValueError if the requested backup doesn't exist or is corrupted.
    """
    # Load the target backup first. If it's missing or corrupted, bail
    # before we create a counter-backup — no point taking a counter-
    # snapshot for a restore that can't proceed.
    target = get_backup(backup_id)
    if target is None:
        raise ValueError(f"Backup {backup_id} not found")

    document_id = target["document_id"]

    # Counter-backup of current state.
    counter_id = create_backup(
        document_id=document_id,
        trigger_type=TRIGGER_PRE_RESTORE,
        entries=current_entries,
        metadata_subset=current_metadata_subset,
        label=f"Auto-saved before restoring backup {backup_id}",
    )

    logging.info(
        "backups_manager: restoring backup %s for doc %s "
        "(counter-backup %s created).",
        backup_id, document_id, counter_id
    )

    return {
        "restored_payload": target["payload"],
        "counter_backup_id": counter_id,
    }


def delete_backup(backup_id: int) -> bool:
    """Delete a single backup. Returns True if a row was deleted."""
    return db.db_delete_backup(backup_id)
