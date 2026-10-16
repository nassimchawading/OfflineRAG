"""Part 4 (updated in Part 7b): extract the text of the documents of data/catalog.csv, page by page.

For each document writes data/extracted/<name>__<id>.jsonl with one JSON line per page:
    {"book": "Books\\RDM\\RdM_print.pdf", "page": 1, "text": "...", "n_chars": 124, "n_images": 1}
"book" is the path inside data/pdfs: unique, unlike file names (there are several "Introduction.pdf").
"page" is the 1-based page number as shown in a PDF viewer (used later for citations).

Documents that already have a .jsonl file are skipped, so the script can be re-run safely.

Run (after src\\catalog.py):  .venv\\Scripts\\python.exe src\\extract.py
"""
from pathlib import Path
import hashlib
import json
import re
import time

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"
OUT_DIR = ROOT / "data" / "extracted"

pymupdf.TOOLS.mupdf_display_errors(False)  # damaged PDFs print many harmless MuPDF warnings


def jsonl_path(book: str) -> Path:
    """data/extracted file of a document: readable name + short hash of its path (unique)."""
    stem = re.sub(r"[^\w-]+", "_", Path(book).stem)[:60]
    return OUT_DIR / f"{stem}__{hashlib.sha1(book.encode('utf-8')).hexdigest()[:8]}.jsonl"


def extract_pdf(pdf_path: Path, book: str) -> list[dict]:
    """Return one record per page with its text and basic counts."""
    records = []
    with pymupdf.open(pdf_path) as doc:
        if doc.needs_pass:
            raise ValueError("password-protected PDF")
        for page in doc:
            # No sort=True: it reads lines across the whole page width and mixes the two columns of
            # 2-column articles. The PDF's own order reads the left column, then the right one.
            text = page.get_text("text").strip()
            records.append({
                "book": book,
                "page": page.number + 1,
                "text": text,
                "n_chars": len(text),
                "n_images": len(page.get_images()),
            })
    return records


def extract_new(books: list[str]) -> list[Path]:
    """Extract every document (path inside data/pdfs) that has no .jsonl yet. Returns the files written."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    todo = [b for b in books if not jsonl_path(b).exists()]
    print(f"  {len(books)} documents: {len(books) - len(todo)} already extracted, {len(todo)} to extract")
    written, start = [], time.time()
    for i, book in enumerate(todo, 1):
        out_path = jsonl_path(book)
        try:
            records = extract_pdf(PDF_DIR / book, book)
        except Exception as e:  # damaged or protected PDF: report it and carry on with the others
            print(f"  FAILED: {book}: {e}")
            continue
        # write to a temp file first, then rename: a crash never leaves a half-written .jsonl
        tmp_path = out_path.with_suffix(".jsonl.tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        tmp_path.replace(out_path)
        written.append(out_path)
        if i % 100 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} extracted ({time.time() - start:.0f} s)", flush=True)
    return written


if __name__ == "__main__":
    from catalog import load_catalog
    extract_new([r["path"] for r in load_catalog() if r["status"] == "ok"])
