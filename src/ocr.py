"""Part 9: OCR of the scanned documents (status "scan" in data/catalog.csv) -> data/extracted/*.jsonl

Uses the Tesseract OCR engine built into PyMuPDF + the French language file in tools/tessdata:
nothing is installed on Windows, the project folder stays portable. Every page is read again by OCR
(full=True), also pages that have a bad text layer (broken font encoding, bad old OCR). The drawings of the
"Divers" category are skipped (images, nothing to read). The PDFs themselves are not changed.

The output has the same format as extract.py (+ "ocr": true), so add_pdfs.py indexes these documents like
the others. Resumable: pages already read are kept in <name>.jsonl.partial; the .jsonl file appears only
when the whole document is done.

Run:  .venv\\Scripts\\python.exe src\\ocr.py           all scanned documents, WORKERS at a time
      .venv\\Scripts\\python.exe src\\ocr.py --test    speed + quality on a few pages (nothing saved)
Then: .venv\\Scripts\\python.exe src\\add_pdfs.py      indexes them
"""
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import json
import sys
import time

import pymupdf

from extract import PDF_DIR, jsonl_path

ROOT = Path(__file__).resolve().parent.parent
TESSDATA = ROOT / "tools" / "tessdata"   # fra.traineddata (French only: user 2026-10-14, the scans are French)
LANGUAGE = "fra"
DPI = 300          # resolution of the page image given to Tesseract (300 = usual value for books)
WORKERS = 4        # documents read at the same time (6-core Ryzen: leave some power for the rest)
SKIP_SUBCATEGORIES = {"Plans & dessins techniques"}

pymupdf.TOOLS.mupdf_display_errors(False)


def ocr_page(page, dpi: int = DPI) -> str:
    tp = page.get_textpage_ocr(language=LANGUAGE, dpi=dpi, full=True, tessdata=str(TESSDATA))
    return page.get_text("text", textpage=tp).strip()


def read_partial(partial: Path) -> list[str]:
    """Pages already done (a crash can leave a half-written last line: it is dropped)."""
    if not partial.exists():
        return []
    good = []
    for line in partial.read_text(encoding="utf-8").splitlines():
        try:
            json.loads(line)
            good.append(line)
        except json.JSONDecodeError:
            break
    return good


def ocr_document(book: str, title: str) -> str:
    """OCR one document (runs in a separate process). Returns a one-line report."""
    out = jsonl_path(book)
    partial = out.with_suffix(".jsonl.partial")
    done = read_partial(partial)
    partial.write_text("".join(line + "\n" for line in done), encoding="utf-8")
    start, empty = time.time(), 0
    with pymupdf.open(PDF_DIR / book) as doc, open(partial, "a", encoding="utf-8") as f:
        n = doc.page_count
        for i in range(len(done), n):
            page = doc[i]
            text = ocr_page(page)
            empty += len(text) < 50
            f.write(json.dumps({"book": book, "page": i + 1, "text": text, "n_chars": len(text),
                                "n_images": len(page.get_images()), "ocr": True}, ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % 50 == 0:
                rate = (time.time() - start) / (i + 1 - len(done))
                print(f"  {title[:40]}: {i + 1}/{n} pages ({rate:.1f} s/page, ~{rate * (n - i - 1) / 60:.0f} min left)",
                      flush=True)
    partial.replace(out)
    return f"done: {title[:50]} ({n} pages, {time.time() - start:.0f} s, {empty} pages almost empty)"


def scanned_documents() -> list[dict]:
    from catalog import load_catalog
    rows = [r for r in load_catalog() if r["status"] == "scan" and r["subcategory"] not in SKIP_SUBCATEGORIES]
    return sorted(rows, key=lambda r: -int(r["pages"] or 0))   # longest first: better use of the workers


def test() -> None:
    """Time and show the OCR of the middle page of 3 scanned books, at 2 resolutions."""
    for r in scanned_documents()[::10][:3]:
        with pymupdf.open(PDF_DIR / r["path"]) as doc:
            page = doc[doc.page_count // 2]
            for dpi in (200, 300):
                start = time.time()
                text = ocr_page(page, dpi)
                print(f"\n=== {r['title'][:50]} p.{page.number + 1}, {dpi} dpi: {time.time() - start:.1f} s, "
                      f"{len(text)} characters\n{' '.join(text.split())[:400]}")


def main() -> None:
    if not (TESSDATA / "fra.traineddata").exists():
        sys.exit(f"missing {TESSDATA / 'fra.traineddata'} (see INSTALL_LOG.md)")
    if "--test" in sys.argv[1:]:
        test()
        return
    todo = [r for r in scanned_documents() if not jsonl_path(r["path"]).exists()]
    pages = sum(int(r["pages"] or 0) for r in todo)
    print(f"{len(todo)} scanned documents to OCR, {pages:,} pages, {WORKERS} at a time")
    with ProcessPoolExecutor(WORKERS) as pool:
        jobs = [pool.submit(ocr_document, r["path"], r["title"]) for r in todo]
        for job in as_completed(jobs):
            print(job.result(), flush=True)
    print("OCR finished. Next: .venv\\Scripts\\python.exe src\\add_pdfs.py  (indexes the OCR'd documents)")


if __name__ == "__main__":
    main()
