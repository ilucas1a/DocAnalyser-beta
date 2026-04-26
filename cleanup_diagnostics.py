"""
cleanup_diagnostics.py — Remove diagnostic artefacts left behind by the
P7/P8 investigations on 26 April 2026. Safe to run once both fixes are
verified working (which they now are).

Run:
    python cleanup_diagnostics.py        # dry-run, lists what would be deleted
    python cleanup_diagnostics.py --yes  # actually delete

The deleted files are all in Git history if ever needed back. They were:

  - diagnose_digest{.py, _output.txt}
  - diagnose_digest_2{.py, _output.txt}
  - diagnose_digest_3{.py, _output.txt}
        Three successive diagnostic scripts written to investigate the
        P8 subscription digest bug, finding the root cause (174 of 181
        ai_responses had is_deleted=1, hidden from the digest by a
        WHERE filter in db_get_all_documents).

  - dump_digest_dialog.py
  - find_softdelete.py
        Helper scripts written but never invoked during P8.

  - find_metadata_rendering.py
        Helper for locating where the Thread Viewer renders the
        metadata block during the docx hyperlink follow-up. Never run -
        Ian confirmed the Thread Viewer Source link was already working
        before the script was needed.

  - Documentation/ProjectMap/14_ROADMAP_STATUS.md.tmp_p8_append
        A draft fragment of the P8 roadmap entry that was accidentally
        written as a separate file; the content was inlined into the
        main roadmap doc directly afterwards.
"""

import os
import sys


PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))


# All paths here are relative to the project root (PROJECT_DIR).
FILES_TO_DELETE = [
    # P8 diagnostic scripts and their outputs
    "diagnose_digest.py",
    "diagnose_digest_2.py",
    "diagnose_digest_3.py",
    "diagnose_digest_output.txt",
    "diagnose_digest_2_output.txt",
    "diagnose_digest_3_output.txt",

    # P8 helper scripts that were drafted but never run
    "dump_digest_dialog.py",
    "find_softdelete.py",

    # P7 follow-up helper - not needed once Thread Viewer was confirmed
    # to already make URLs clickable via _make_links_clickable.
    "find_metadata_rendering.py",

    # Stray draft fragment from the P8 roadmap entry being inlined.
    os.path.join("Documentation", "ProjectMap",
                 "14_ROADMAP_STATUS.md.tmp_p8_append"),
]


def main():
    dry_run = "--yes" not in sys.argv

    print("Cleanup of P7 / P8 investigation diagnostics")
    if dry_run:
        print("Mode: DRY RUN (use --yes to actually delete)")
    else:
        print("Mode: ACTUAL DELETE")
    print()

    deleted = 0
    pending = 0
    missing = 0
    errors  = 0

    for rel_path in FILES_TO_DELETE:
        abs_path = os.path.join(PROJECT_DIR, rel_path)

        if not os.path.exists(abs_path):
            print(f"  [MISSING]   {rel_path}")
            missing += 1
            continue

        if dry_run:
            print(f"  [WOULD DEL] {rel_path}")
            pending += 1
            continue

        try:
            os.remove(abs_path)
            print(f"  [DELETED]   {rel_path}")
            deleted += 1
        except Exception as exc:
            print(f"  [ERROR]     {rel_path}: {exc}")
            errors += 1

    print()
    if dry_run:
        print(f"Dry run: would delete {pending} file(s); "
              f"{missing} already absent.")
        print("Re-run with --yes to actually delete.")
    else:
        print(f"Deleted {deleted} file(s); "
              f"{missing} already absent; {errors} error(s).")
        print("All deleted files are recoverable from Git history if needed.")


if __name__ == "__main__":
    main()
