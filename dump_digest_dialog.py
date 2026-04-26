"""Quick grep for how DigestDialog calls generate_digest."""
import re

with open(r"C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\subscription_dialog.py",
          "r", encoding="utf-8") as fh:
    text = fh.read()

# Find class DigestDialog and methods like _run_digest, _on_generate, etc.
# Print everything from "class DigestDialog" to end-of-file (or next class).
m = re.search(r"^class DigestDialog\b", text, re.MULTILINE)
if not m:
    print("DigestDialog class not found")
else:
    start = m.start()
    # Find the next 'class ...' after DigestDialog
    next_m = re.search(r"^class \w+\b", text[start + 1:], re.MULTILINE)
    if next_m:
        end = start + 1 + next_m.start()
    else:
        end = len(text)
    block = text[start:end]
    print(f"=== DigestDialog block: {len(block)} chars, {block.count(chr(10))} lines ===")
    print(block)

with open(r"C:\Ian\Python\GetTextFromYouTube\DocAnalyzer_DEV\digest_dialog_dump.txt",
          "w", encoding="utf-8") as fh:
    fh.write(block if m else "DigestDialog class not found")
