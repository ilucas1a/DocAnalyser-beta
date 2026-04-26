"""Find soft-delete code paths in document_library.py."""
import re

with open(r"C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\document_library.py",
          "r", encoding="utf-8") as fh:
    text = fh.read()

# Find any line containing is_deleted, soft-delete-style updates, or
# UPDATE...is_deleted=1 patterns.
for i, line in enumerate(text.splitlines(), start=1):
    if any(marker in line.lower() for marker in
           ["is_deleted", "soft delete", "soft-delete",
            "db_delete_document", "is_deleted = 1", "is_deleted=1"]):
        print(f"{i:5d}: {line}")

# Also dump add_document_to_library function
m = re.search(r"def add_document_to_library\b", text)
if m:
    start = m.start()
    # find next def at module level
    next_m = re.search(r"^def \w+\b", text[start + 1:], re.MULTILINE)
    end = start + 1 + next_m.start() if next_m else len(text)
    print("\n=== add_document_to_library ===")
    print(text[start:end])
