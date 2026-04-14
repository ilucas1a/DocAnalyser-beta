"""
repair_corruption.py  -  DocAnalyser database corruption repair
Run from DocAnalyzer_DEV with the venv active:
    python repair_corruption.py
"""
import os, re, json, sqlite3, shutil
from datetime import datetime

APP_NAME = "DocAnalyser_Beta"
APPDATA  = os.getenv("APPDATA") or os.path.expanduser("~")
DATA_DIR = os.path.join(APPDATA, APP_NAME)
DB_PATH  = os.path.join(DATA_DIR, "docanalyser.db")

ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP = DB_PATH + f".backup_{ts}"
shutil.copy2(DB_PATH, BACKUP)
print(f"Backup created: {BACKUP}\n")


def extract_first_paragraph(content):
    m = re.search(r'\n\n\[[\d]', content)
    if m:
        return content[:m.start()].strip()
    m = re.search(r'\n\[[\d]', content)
    if m and m.start() > 20:
        return content[:m.start()].strip()
    matches = list(re.finditer(r'\[[\d]{1,2}:[\d]{2}(?::[\d]{2})?\]', content))
    if len(matches) >= 2:
        candidate = content[:matches[1].start()].strip()
        if len(candidate) > 20:
            return candidate
    return content.strip()


def rebuild_sentences(text, start, end, speaker):
    parts = [p.strip() for p in re.split(r'(?<=[.!?])\s+', text) if p.strip()]
    if not parts:
        parts = [text.strip()]
    dur   = max(0.0, end - start)
    total = sum(len(p) for p in parts) or 1
    result, t = [], start
    for part in parts:
        frac  = len(part) / total
        t_end = t + dur * frac
        result.append({"text": part, "start": t, "end": t_end, "speaker": speaker})
        t = t_end
    return result


conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
total_repaired = 0

docs = conn.execute("""
    SELECT id, title FROM documents
    WHERE is_deleted = 0 AND doc_type = 'audio_transcription'
    ORDER BY updated_at DESC
""").fetchall()

for doc in docs:
    doc_id = doc["id"]
    title  = doc["title"]

    entries = conn.execute("""
        SELECT position, content, metadata
        FROM document_entries
        WHERE doc_id = ?
        ORDER BY position
    """, (doc_id,)).fetchall()

    if not entries:
        continue

    suspicious = [e for e in entries if len(e["content"]) > 2000]
    if not suspicious:
        continue

    print(f"Document: {title}  ({doc_id})")
    print(f"  {len(entries)} entries, {len(suspicious)} suspicious (>2000 chars)")

    repaired = 0
    for entry in entries:
        content  = entry["content"]
        position = entry["position"]
        clen     = len(content)

        if clen <= 2000:
            continue

        fixed = extract_first_paragraph(content)

        if fixed == content.strip():
            print(f"  WARNING pos {position:3d}: {clen:,} chars - no boundary found, skipping")
            continue

        if len(fixed) < 10:
            print(f"  WARNING pos {position:3d}: recovered text too short ({len(fixed)} chars), skipping")
            continue

        try:
            meta = json.loads(entry["metadata"]) if entry["metadata"] else {}
        except Exception:
            meta = {}

        start_t = float(meta.get("start", 0.0))
        end_t   = float(meta.get("end", start_t + 5.0))
        speaker = meta.get("speaker", "")
        meta["sentences"] = rebuild_sentences(fixed, start_t, end_t, speaker)
        meta.pop("text", None)
        new_meta = json.dumps(meta, ensure_ascii=False)

        conn.execute(
            "UPDATE document_entries SET content = ?, metadata = ? "
            "WHERE doc_id = ? AND position = ?",
            (fixed, new_meta, doc_id, position)
        )

        print(f"  FIXED pos {position:3d}: {clen:,} -> {len(fixed):,} chars  |  {repr(fixed[:70])}")
        repaired += 1

    if repaired:
        conn.commit()
        total_repaired += repaired
        print(f"  Repaired {repaired} entries.\n")
    else:
        print(f"  Nothing repaired.\n")

# Fix runaway sentence counts
print("Checking for runaway sentence metadata...")
bloated = conn.execute("""
    SELECT doc_id, position, content, metadata
    FROM document_entries
    WHERE length(metadata) > 50000
""").fetchall()

for row in bloated:
    try:
        meta = json.loads(row["metadata"])
    except Exception:
        continue
    sents = meta.get("sentences", [])
    if len(sents) <= 100:
        continue
    text    = row["content"].strip()
    start_t = float(meta.get("start", 0.0))
    end_t   = float(meta.get("end", start_t + 5.0))
    speaker = meta.get("speaker", "")
    old_count = len(sents)
    meta["sentences"] = rebuild_sentences(text, start_t, end_t, speaker)
    conn.execute(
        "UPDATE document_entries SET metadata = ? WHERE doc_id = ? AND position = ?",
        (json.dumps(meta, ensure_ascii=False), row["doc_id"], row["position"])
    )
    print(f"  FIXED runaway: doc={row['doc_id']} pos={row['position']} "
          f"({old_count} -> {len(meta['sentences'])} sentences)")
    total_repaired += 1

conn.commit()
conn.close()

print(f"\n{'='*60}")
print(f"Repair complete. Total entries fixed: {total_repaired}")
print(f"Backup: {BACKUP}")
