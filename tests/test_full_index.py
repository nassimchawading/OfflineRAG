"""Part 7b check after the full indexing: every "ok" document is in the database, chunks per category,
size on disk, and a few searches in different categories (with and without menu filter).

Run (Ollama must be running):  .venv\\Scripts\\python.exe tests\\test_full_index.py
"""
from collections import Counter
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import index
from catalog import load_catalog
from search import cite, menu_filter, search

col = index.get_collection()
start = time.time()
metas, total = [], col.count()
for offset in range(0, total, 10000):  # one big get() fails ("too many SQL variables"): read by pages
    metas += col.get(include=["metadatas"], limit=10000, offset=offset)["metadatas"]
print(f"{len(metas):,} chunks in the database (read in {time.time() - start:.0f} s)")
size = sum(f.stat().st_size for f in (ROOT / "db").rglob("*") if f.is_file())
print(f"db folder: {size / 1e9:.2f} GB")

books_in_db = Counter(m["book"] for m in metas)
ok = [r for r in load_catalog() if r["status"] == "ok"]
missing = [r for r in ok if r["path"] not in books_in_db]
extra = set(books_in_db) - {r["path"] for r in ok}
print(f"documents: {len(ok)} ok in the catalogue, {len(books_in_db)} in the database, "
      f"{len(missing)} missing, {len(extra)} unknown")
for r in missing[:10]:
    print("   missing:", r["path"])

print("\nchunks per category (documents):")
docs_per_cat = Counter(r["category"] for r in ok if r["path"] in books_in_db)
for cat, n in Counter(m["category"] for m in metas).most_common():
    print(f"  {n:7,}  ({docs_per_cat[cat]:4} docs)  {cat}")
print("by source:", dict(Counter(m["source"] for m in metas)))

tests = [
    ("Comment fonctionne une machine asynchrone ?", None),
    ("Quelle est la différence entre trempe et revenu d'un acier ?", None),
    ("Qu'est-ce que la méthode AMDEC ?", None),
    ("Comment mesurer un débit dans une conduite ?", None),
    ("Comment calculer la flèche d'une poutre ?", None),
    ("Qu'est-ce que le moulage par injection des thermoplastiques ?", menu_filter(category="Plastiques & composites")),
    ("What is a PID controller?", None),   # English: search works on the meaning
    ("Comment calculer la flèche d'une poutre ?", menu_filter(category="Informatique")),  # wrong menu
]
for q, where in tests:
    start = time.time()
    hits = search(q, k=3, where=where)
    print(f"\n=== {q}  [{'menu ' + str(where) if where else 'tous'}]  ({time.time() - start:.1f} s)")
    for h in hits:
        print(f"  [{h['distance']:.3f}] {h['category'][:28]:28} | {cite(h)[:75]}")
