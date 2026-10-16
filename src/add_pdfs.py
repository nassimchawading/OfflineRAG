"""Part 7: add new PDFs to the chatbot with one command.

Put the new PDFs in data/pdfs (any sub-folder; delete the ones you no longer want), then run
(Ollama must be running for step 3):
    .venv\\Scripts\\python.exe src\\add_pdfs.py               check, ask, then index
    .venv\\Scripts\\python.exe src\\add_pdfs.py --check-only  steps 0-2 only, nothing indexed or removed
    .venv\\Scripts\\python.exe src\\add_pdfs.py --yes         don't ask before removing / indexing
    .venv\\Scripts\\python.exe src\\add_pdfs.py --limit 20    index only 20 documents (to test)

0. catalogue (catalog.py): new files, duplicates, scans, category of every document -> data/catalog.csv.
   Documents no longer in the catalogue (deleted PDFs): after asking, removed from the database.
1. extract the text of every "ok" document not extracted yet (extract.py)
2. quality check of the documents not yet in the database: headers/footers the cleaning rules
   don't remove, number of chunks + indexing time
3. embed and store the new chunks (index.py). Resumable: if the laptop sleeps or crashes, run
   the script again and it continues where it stopped.
"""
from collections import Counter
from pathlib import Path
import ctypes
import json
import sys

import ollama

import catalog
import index
from chunking import clean_book, load_records, make_chunks
from extract import extract_new, jsonl_path
from ocr import SKIP_SUBCATEGORIES

CHUNKS_PER_S = 16      # indexing speed measured in Part 5


def book_of(jsonl: Path) -> str:
    """Document of an extracted file, read from its first line only (fast for big books)."""
    with open(jsonl, encoding="utf-8") as f:
        first = f.readline()
    return json.loads(first)["book"] if first.strip() else ""


def forget_book(collection, jsonl: Path) -> None:
    """Remove a document from the database and delete its extracted text, so the chatbot stops using it."""
    book = book_of(jsonl)
    n = len(collection.get(where={"book": book}, include=[])["ids"])
    collection.delete(where={"book": book})
    jsonl.unlink()
    print(f"  removed {book}: {n} chunks deleted from the database, {jsonl.name} deleted")


def check_book(jsonl: Path) -> tuple[int, str]:
    """(number of chunks, warning or ''). Warns about lines repeated on many pages after cleaning
    (header/footer that chunking.py does not remove)."""
    records = load_records(jsonl)
    texts = [c for c, _ in clean_book(records) if c]
    edges = Counter()
    for t in texts:
        lines = t.splitlines()
        edges.update({lines[0], lines[-1]})  # a set, so a one-line page counts once
    repeated = [line for line, n in edges.most_common(3) if n >= max(4, 0.2 * len(texts))]
    warning = f"repeated line {repeated[0][:60]!r}" if repeated else ""
    return len(make_chunks(records)), warning


def ollama_ready() -> bool:
    try:
        models = [m.model for m in ollama.list().models]
    except Exception:
        print("\nOllama is not running. In another PowerShell window:")
        print("  cd C:\\Users\\Nassim\\Documents\\OfflineRAG")
        print("  powershell -NoProfile -ExecutionPolicy Bypass -File .\\start_ollama.ps1")
        print("then run this script again (the extraction already done is kept).")
        return False
    if not any(m.split(":")[0] == index.EMBED_MODEL for m in models):
        print(f"\nThe embedding model {index.EMBED_MODEL} is not installed in Ollama.")
        return False
    return True


def confirm(question: str) -> bool:
    # strip "\ufeff": PowerShell can put an invisible byte-order mark before piped answers
    return input(question).strip().lstrip("\ufeff").lower() in ("y", "yes", "o", "oui")


def keep_awake(on: bool) -> None:
    """Ask Windows not to sleep while indexing runs. Only lasts while this script runs;
    closing the laptop lid can still put it to sleep (then just re-run the script)."""
    if sys.platform == "win32":
        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0))


def main() -> None:
    args = sys.argv[1:]
    check_only, yes = "--check-only" in args, "--yes" in args
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None

    print("Step 0/3: catalogue of data/pdfs")
    rows = catalog.build()
    catalog.write_csv(rows, catalog.CATALOG)
    status = Counter(r["status"] for r in rows)
    ok = [r for r in rows if r["status"] == "ok"]
    scans = [r for r in rows if r["status"] == "scan"]
    ocr_done = [r for r in scans if jsonl_path(r["path"]).exists()]   # text made by src/ocr.py
    drawings = [r for r in scans if r["subcategory"] in SKIP_SUBCATEGORIES]  # images: ocr.py skips them
    waiting = len(scans) - len(ocr_done) - len(drawings)
    print(f"  {len(ok)} documents ok, {len(scans)} scanned: {len(ocr_done)} OCR'd (indexed like the others), "
          f"{len(drawings)} drawings (images, not OCR'd)"
          + (f", {waiting} waiting for OCR (src\\ocr.py)" if waiting else ""))
    tidy = status["duplicate"] + status["empty"] + status["not_pdf"]
    if tidy:
        print(f"  {tidy} duplicate/empty/non-PDF files are skipped; to move them out of data/pdfs run:"
              f" .venv\\Scripts\\python.exe src\\catalog.py --clean")

    collection = index.get_collection()
    known = {r["path"] for r in ok + scans}
    removed = [p for p in sorted(index.EXTRACTED_DIR.glob("*.jsonl")) if book_of(p) not in known]
    if removed:
        print("\nDocuments no longer in data/pdfs (or no longer ok) but still known by the chatbot:")
        for p in removed[:20]:
            print(f"  {book_of(p)}")
        if len(removed) > 20:
            print(f"  ... and {len(removed) - 20} more")
        if check_only:
            print("  (--check-only: kept)")
        elif yes or confirm("Remove them from the chatbot too? [y/N] "):
            for p in removed:
                forget_book(collection, p)
        else:
            print("  kept: the chatbot can still answer from them")

    print("\nStep 1/3: extracting the text of new documents")
    extract_new([r["path"] for r in ok])

    print("\nStep 2/3: check of the documents not yet in the database")
    indexed, pending = [], []
    for r in ok + ocr_done:
        if not jsonl_path(r["path"]).exists():
            continue  # extraction failed
        has_chunks = collection.get(where={"book": r["path"]}, limit=1, include=[])["ids"]
        (indexed if has_chunks else pending).append(r)
    if limit is not None:
        pending = pending[:limit]
    total, warnings = 0, []
    for r in pending:
        n, warning = check_book(jsonl_path(r["path"]))
        total += n
        if warning:
            warnings.append(f"{r['title'][:45]}: {warning}")
    print(f"  {len(indexed)} already indexed, {len(pending)} to index: {total:,} chunks, "
          f"~{total / CHUNKS_PER_S / 60:.0f} min")
    if warnings:
        print(f"  {len(warnings)} documents keep a repeated header/footer line (harmless noise), e.g.:")
        for w in warnings[:5]:
            print(f"    {w}")
    by_cat = Counter(r["category"] for r in pending)
    for cat, n in by_cat.most_common():
        print(f"    {n:5}  {cat}")

    if check_only:
        print("\n--check-only: nothing indexed.")
        return
    if pending and not yes and not confirm(f"\nIndex these {len(pending)} document(s) now? [y/N] "):
        print("Not indexed. Run the script again when ready (extraction is not redone).")
        return

    print("\nStep 3/3: indexing (also finishes any document whose indexing was interrupted)")
    if not ollama_ready():
        return
    keep_awake(True)
    try:
        index.main(indexed + pending)
    finally:
        keep_awake(False)
    print("\nDone. The chatbot (src\\ask.py) now searches the new documents too.")


if __name__ == "__main__":
    main()
