"""Part 5: clean extracted pages and split them into chunks for the vector database.

Input:  data/extracted/<name>.jsonl  (one record per PDF page, from extract.py)
Output: list of chunks, each about MAX_CHARS characters, with book + page metadata.

Cleaning rules come from the Part 4 inspection of MR TRACTION.pdf (notes/part4_extraction.md).
New PDFs with other layouts may need extra rules here.
"""
from collections import Counter
from pathlib import Path
import json
import re
import unicodedata

MAX_CHARS = 1500      # ~250 words / ~400 tokens: 4-5 chunks + question fit the 4096-token chat model
OVERLAP_CHARS = 200   # repeat the end of a chunk at the start of the next, so ideas cut in two are not lost

# Footer like "3-32      TAF   MR2   06   A   01"  or  "TAF   MR2   06   A   01     5-279"
FOOTER_RE = re.compile(r"TAF\s+MR2\s+\d+\s+A\s+\d+")
PRINTED_PAGE_RE = re.compile(r"\b(\d{1,2}-\d{1,4})\b")
# Header lines of the sub-documents: "TAF-MR2-06A--06A-TC048", "Matériel roulant   page", "TAF   5 / 44"
HEADER_RES = [
    re.compile(r"^TAF-MR2-[\w-]+$"),
    re.compile(r"^(page\s*)?Matériel roulant(\s*page)?$"),
    re.compile(r"^(TAF\s*)?\d+\s*/\s*\d+(\s*TAF)?$"),
]
TOC_LINE_RE = re.compile(r"\.{5,}")  # dotted leaders "Courbe de la tension.........3-40"
SEPARATOR_RE = re.compile(r"^[_\-—=.\s]{5,}$")  # rule lines "__________"
REPEAT_SHARE = 0.4  # a line found on >= 40% of a book's pages is a header/footer, whatever the layout


def clean_page(text: str) -> tuple[str, str | None]:
    """Remove headers/footers. Returns (clean text, printed page number like '3-32' or None)."""
    # NFKC: ligatures from the PDF fonts become normal letters ("déﬁnition" -> "définition")
    text = unicodedata.normalize("NFKC", text)
    printed_page = None
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if SEPARATOR_RE.match(stripped):
            continue
        if FOOTER_RE.search(stripped):
            m = PRINTED_PAGE_RE.search(FOOTER_RE.sub("", stripped))
            if m:
                printed_page = m.group(1)
            continue
        if any(r.match(stripped) for r in HEADER_RES):
            continue
        kept.append(re.sub(r"[ \t]{2,}", " ", stripped))  # layout spaces -> one space
    clean = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return clean, printed_page


def _line_key(line: str) -> str:
    """Compare lines without digits, underscores and spaces: 'H 2 546 − 3' == 'H 2 546 − 4'."""
    return re.sub(r"[\d_\s]+", " ", line).strip().lower()


def clean_book(records: list[dict]) -> list[tuple[str, str | None]]:
    """clean_page on every page, then drop the lines repeated on many pages of this book: headers
    and footers of any layout (e.g. '© Techniques de l'Ingénieur, traité Informatique').
    Keys need 3+ letters, so lines of numbers (table values) are never removed."""
    pages = [clean_page(r["text"]) for r in records]
    counts = Counter()
    for text, _ in pages:
        counts.update({k for k in map(_line_key, text.splitlines()) if sum(c.isalpha() for c in k) >= 3})
    min_pages = max(3, REPEAT_SHARE * len(pages))
    boilerplate = {k for k, n in counts.items() if n >= min_pages}
    out = []
    for text, printed in pages:
        kept = [l for l in text.splitlines() if _line_key(l) not in boilerplate]
        out.append((re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), printed))
    return out


def is_skippable(clean: str) -> bool:
    """Blank pages, 'PAGE BLANCHE' pages and table-of-contents pages carry no answers.
    Short pages are kept: most are full-page figures whose caption ("Fig. 1-4 ...") is useful."""
    if len(clean) < 10 or "PAGE BLANCHE" in clean.upper():
        return True
    lines = [l for l in clean.splitlines() if l.strip()]
    return sum(bool(TOC_LINE_RE.search(l)) for l in lines) >= 0.3 * len(lines)


def _paragraphs(text: str) -> list[str]:
    """Split on blank lines; split paragraphs that are too long on single lines."""
    out = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if len(para) <= MAX_CHARS:
            out.append(para)
        else:
            out.extend(l for l in para.splitlines() if l.strip())
    return [p for p in out if p]


def make_chunks(records: list[dict]) -> list[dict]:
    """Group paragraphs of consecutive pages into chunks of up to MAX_CHARS characters."""
    chunks = []
    current: list[tuple[str, dict]] = []  # (paragraph, page info)

    def flush():
        if not current:
            return
        pages = [info for _, info in current]
        chunks.append({
            "id": f"{pages[0]['book']}::{len(chunks):05d}",
            "text": "\n".join(p for p, _ in current),
            "book": pages[0]["book"],
            "page_start": pages[0]["page"],
            "page_end": pages[-1]["page"],
            "printed_start": pages[0]["printed"] or "",
            "printed_end": pages[-1]["printed"] or "",
        })

    for rec, (clean, printed) in zip(records, clean_book(records)):
        if is_skippable(clean):
            continue
        info = {"book": rec["book"], "page": rec["page"], "printed": printed}
        for para in _paragraphs(clean):
            if current and sum(len(p) + 1 for p, _ in current) + len(para) > MAX_CHARS:
                flush()
                # overlap: carry the last paragraph(s) over, up to OVERLAP_CHARS
                carry, size = [], 0
                for p, i in reversed(current):
                    if size + len(p) > OVERLAP_CHARS:
                        break
                    carry.insert(0, (p, i))
                    size += len(p)
                current = carry
            current.append((para, info))
    flush()
    return chunks


def load_records(jsonl_path: Path) -> list[dict]:
    with open(jsonl_path, encoding="utf-8") as f:
        return [json.loads(line) for line in f]
