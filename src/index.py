"""Part 5 (updated in Part 7b): embed the chunks with bge-m3 (via Ollama) and store them in ChromaDB.

For every "ok" document of data/catalog.csv that is extracted (data/extracted), chunks it (chunking.py),
embeds the chunks and saves them in the vector database in db/, with the document's title, category,
subcategory, themes and source, so the app can search inside one menu or one theme only. Chunks already in the database
are skipped, so the script can be stopped and re-run at any time (resumable).

Run (Ollama must be running):  .venv\\Scripts\\python.exe src\\index.py
"""
from pathlib import Path
import time

import chromadb
import ollama
from chromadb.config import Settings

from chunking import load_records, make_chunks
from extract import jsonl_path
from taxonomy import THEMES, theme_key

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = ROOT / "data" / "extracted"
DB_DIR = ROOT / "db"
COLLECTION = "manuals"
EMBED_MODEL = "bge-m3"   # multilingual (French + English) embedding model
BATCH = 16               # chunks embedded per request to Ollama
DOC_FIELDS = ("title", "category", "subcategory", "themes", "source", "ti_code")  # copied from the catalogue


def get_collection():
    client = chromadb.PersistentClient(path=str(DB_DIR), settings=Settings(anonymized_telemetry=False))
    # cosine distance: 0 = same meaning, larger = less related
    return client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def embed(texts: list[str], on_gpu: bool = True) -> list[list[float]]:
    """on_gpu=False runs bge-m3 on the CPU: fast enough for one question, and it leaves the GPU
    to the chat model so the two models don't keep swapping (4 GB of VRAM can't hold both)."""
    options = None if on_gpu else {"num_gpu": 0}
    return ollama.embed(model=EMBED_MODEL, input=texts, options=options).embeddings


def doc_metadata(row: dict) -> dict:
    """Catalogue fields + one yes/no field per theme (ChromaDB can filter on a field, not inside a list)."""
    doc = {k: row.get(k) or "" for k in DOC_FIELDS}
    doc_themes = set(doc["themes"].split(" | "))
    return doc | {theme_key(t): t in doc_themes for t in THEMES}


def index_book(collection, row: dict) -> int:
    """Index one catalogue document. Returns the number of chunks added."""
    chunks = make_chunks(load_records(jsonl_path(row["path"])))
    if not chunks:
        return 0
    existing = set(collection.get(ids=[c["id"] for c in chunks], include=[])["ids"])
    todo = [c for c in chunks if c["id"] not in existing]
    doc = doc_metadata(row)
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        collection.add(
            ids=[c["id"] for c in batch],
            documents=[c["text"] for c in batch],
            embeddings=embed([c["text"] for c in batch]),
            metadatas=[{k: c[k] for k in ("book", "page_start", "page_end", "printed_start", "printed_end")} | doc
                       for c in batch],
        )
    return len(todo)


def sync_metadata(collection, row: dict) -> bool:
    """If the category/title of an indexed document changed in the catalogue, update its chunks."""
    first = collection.get(where={"book": row["path"]}, limit=1, include=["metadatas"])
    if not first["ids"]:
        return False
    doc = doc_metadata(row)
    if all(first["metadatas"][0].get(k) == v for k, v in doc.items()):
        return False
    res = collection.get(where={"book": row["path"]}, include=["metadatas"])
    collection.update(ids=res["ids"], metadatas=[m | doc for m in res["metadatas"]])
    return True


def main(rows: list[dict] | None = None) -> None:
    """Index the given catalogue rows (default: every "ok" document that is extracted)."""
    if rows is None:
        from catalog import load_catalog
        rows = [r for r in load_catalog() if r["status"] in ("ok", "scan")]  # scans: once OCR'd (ocr.py)
    rows = [r for r in rows if jsonl_path(r["path"]).exists()]
    collection = get_collection()
    synced = sum(sync_metadata(collection, row) for row in rows)
    if synced:
        print(f"  labels (title/category/themes) updated for {synced} already indexed documents")
    start, added, first = time.time(), 0, None
    for i, row in enumerate(rows, 1):
        before = time.time()
        n = index_book(collection, row)
        added += n
        if n:
            if first is None:  # time the documents that really need indexing, not the ones already done
                start, first = before, i - 1
            elapsed = time.time() - start
            left = elapsed / (i - first) * (len(rows) - i)
            print(f"  [{i}/{len(rows)}] {row['title'][:55]}: {n} chunks "
                  f"({added / elapsed:.1f} chunks/s, ~{left / 60:.0f} min left)", flush=True)
    print(f"database now holds {collection.count()} chunks in {DB_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
