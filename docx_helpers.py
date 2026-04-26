"""
docx_helpers.py - Low-level helpers for building Word .docx documents.

These helpers wrap python-docx's underlying XML structures to add
features that python-docx doesn't expose directly:

    add_external_hyperlink(paragraph, url, text)      # https://...
    add_internal_hyperlink(paragraph, anchor, text)   # link to a bookmark
    add_bookmark(paragraph, name)                     # named anchor target

python-docx has no first-class API for any of these, but the underlying
OOXML format supports them well; this module assembles the XML elements
directly via OxmlElement / qn().

Used by document_export.py and thread_viewer_metadata.py.

Why a separate module?
----------------------
Both document_export.py and thread_viewer_metadata.py need these
helpers, and document_export.py already imports thread_viewer_metadata
(for MetadataBlock).  Putting the helpers in a third, dependency-free
module avoids the circular-import problem and keeps each helper to one
canonical implementation.

Bookmark IDs
------------
Word requires every bookmark in a document to have a unique numeric id
on its <w:bookmarkStart>/<w:bookmarkEnd> elements.  add_bookmark() picks
the next free id by scanning the document's existing bookmarks rather
than using a Python-side counter — that way the id allocation is
correct even if the same Document object is built up across multiple
calls or multiple modules without a shared counter.
"""

from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


# ─────────────────────────────────────────────────────────────────────────────
# Bookmarks
# ─────────────────────────────────────────────────────────────────────────────

def _next_bookmark_id(paragraph) -> int:
    """Return the next free numeric id by scanning existing bookmarks.

    Walks up to the document root and finds the highest <w:bookmarkStart>
    id already in use, then returns one more.  Robust against being
    called from multiple call sites without a shared Python-side counter.
    """
    # Walk up to the document root (the <w:document> element).
    elem = paragraph._p
    root = elem
    while root.getparent() is not None:
        root = root.getparent()

    max_id = 0
    for bm_start in root.iter(qn("w:bookmarkStart")):
        try:
            bm_id = int(bm_start.get(qn("w:id"), "0"))
            if bm_id > max_id:
                max_id = bm_id
        except (ValueError, TypeError):
            pass
    return max_id + 1


def add_bookmark(paragraph, name: str) -> None:
    """Add a bookmark spanning the entire paragraph.

    Word and Google Docs both navigate to the position of <w:bookmarkStart>
    when following a link to a bookmark, so wrapping the whole paragraph
    is sufficient (and simpler than positioning bookmarks at character
    offsets within runs).

    Args:
        paragraph: a python-docx Paragraph object.
        name:      bookmark name.  Pandoc-style anchor names like
                   'point-1' / 'kp-point-1' / 'sources' work fine.
                   Word's own constraints: must start with a letter,
                   no spaces, max 40 chars; the names produced by the
                   digest generator already obey these.
    """
    if not name:
        return

    bookmark_id = str(_next_bookmark_id(paragraph))

    start = OxmlElement("w:bookmarkStart")
    start.set(qn("w:id"), bookmark_id)
    start.set(qn("w:name"), name)

    end = OxmlElement("w:bookmarkEnd")
    end.set(qn("w:id"), bookmark_id)

    # bookmarkStart goes at the very start of the paragraph (Word jumps
    # there on navigation); bookmarkEnd at the very end so the bookmark
    # spans the visible content of the paragraph.
    paragraph._p.insert(0, start)
    paragraph._p.append(end)


# ─────────────────────────────────────────────────────────────────────────────
# Hyperlinks (external and internal)
# ─────────────────────────────────────────────────────────────────────────────

# Standard Word "Hyperlink" character style colour (matches Word's
# built-in Hyperlink style for visual consistency with regular Word
# documents).
_HYPERLINK_COLOR_HEX = "0563C1"


def _build_hyperlink_run(text: str, bold: bool, italic: bool,
                         font_size_pt) -> "OxmlElement":
    """Build the inner <w:r> element for a hyperlink.

    Renders blue underlined text with optional bold/italic/size, applied
    via run properties (<w:rPr>).
    """
    run_elem = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    color = OxmlElement("w:color")
    color.set(qn("w:val"), _HYPERLINK_COLOR_HEX)
    rPr.append(color)

    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    rPr.append(underline)

    if bold:
        rPr.append(OxmlElement("w:b"))
    if italic:
        rPr.append(OxmlElement("w:i"))

    if font_size_pt is not None:
        # Word stores size in half-points: 10pt → 20.
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), str(int(round(float(font_size_pt) * 2))))
        rPr.append(sz)

    run_elem.append(rPr)

    text_elem = OxmlElement("w:t")
    text_elem.text = text
    text_elem.set(qn("xml:space"), "preserve")
    run_elem.append(text_elem)

    return run_elem


def add_external_hyperlink(paragraph, url: str, text: str,
                           bold: bool = False, italic: bool = False,
                           font_size_pt=None) -> None:
    """Append a clickable external hyperlink (URL) to a paragraph.

    Renders as blue underlined text — the standard Word convention,
    recognised by Word, Google Docs, Outlook, and Pages.  The URL is
    added as an external relationship on the document part so the
    resulting <w:hyperlink> element references it via r:id, exactly the
    way Word itself stores hyperlinks.

    Args:
        paragraph:    a python-docx Paragraph object.
        url:          the target URL (must include scheme).
        text:         the visible link text.
        bold/italic:  optional emphasis on the link text.
        font_size_pt: optional explicit font size; otherwise the link
                      uses the paragraph's inherited size.
    """
    if not url or not text:
        return

    part = paragraph.part
    r_id = part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)
    hyperlink.append(_build_hyperlink_run(text, bold, italic, font_size_pt))

    paragraph._p.append(hyperlink)


def add_internal_hyperlink(paragraph, anchor: str, text: str,
                           bold: bool = False, italic: bool = False,
                           font_size_pt=None) -> None:
    """Append a clickable internal hyperlink (link to a bookmark) to a paragraph.

    Renders identically to an external hyperlink (blue, underlined) but
    targets a w:anchor (bookmark name) rather than an external URL, so
    no relationship is added.  The destination bookmark must be added
    separately via add_bookmark().

    Args:
        paragraph:    a python-docx Paragraph object.
        anchor:       bookmark name to target (without a leading '#').
        text:         the visible link text.
        bold/italic:  optional emphasis on the link text.
        font_size_pt: optional explicit font size.
    """
    if not anchor or not text:
        return

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)
    hyperlink.append(_build_hyperlink_run(text, bold, italic, font_size_pt))

    paragraph._p.append(hyperlink)
