"""Part 7b test: index a small sample of documents, then check that the menu filters work.

Indexes 2 short TI articles of 5 categories (the full indexing later skips them), then asks the same
question with and without a menu filter and prints where the passages come from.

Run (Ollama must be running):  .venv\\Scripts\\python.exe tests\\test_menus.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import index
from catalog import load_catalog
from extract import jsonl_path
from search import cite, menu_filter, search
from taxonomy import SOURCE_TI

CATS = ["Informatique", "Électrotechnique & énergie électrique", "Génie mécanique & calcul",
        "Matériaux métalliques & traitements", "Mesures, métrologie & contrôle"]

rows = [r for r in load_catalog() if r["status"] == "ok" and jsonl_path(r["path"]).exists()]
sample = [r for r in rows if r["ti_code"] == "H2546"]
for cat in CATS:
    small = [r for r in rows if r["category"] == cat and r["source"] == SOURCE_TI and 0 < int(r["pages"] or 0) <= 12]
    sample += small[:2]
print("sample:")
for r in sample:
    print(f"  {r['category'][:30]:30} > {r['subcategory'][:30]:30} | {r['title'][:50]}")
index.main(sample)

question = "Quels bancs d'essai permettent de mesurer la performance d'un processeur ?"
for label, where in [("tous les documents", None),
                     ("Informatique", menu_filter(category="Informatique")),
                     ("Informatique > Architecture & matériel", menu_filter("Informatique", "Architecture & matériel")),
                     ("Techniques de l'Ingénieur", menu_filter(source=SOURCE_TI)),
                     ("Génie mécanique (wrong menu)", menu_filter(category="Génie mécanique & calcul"))]:
    print(f"\n=== {question}  [menu: {label}]")
    for h in search(question, k=3, where=where):
        print(f"  [{h['distance']:.3f}] {h['category'][:25]} > {h['subcategory'][:25]} | {cite(h)[:80]}")

# cross-domain themes: the filter keeps only documents having the theme, whatever their category
for question, theme in [("Comment fonctionne une alimentation à découpage ?", "Électronique de puissance"),
                        ("Comment surveiller les vibrations d'une machine ?", "Vibrations & acoustique"),
                        ("Comment surveiller les vibrations d'une machine ?", "Capteurs")]:
    print(f"\n=== {question}  [thème: {theme}]")
    hits = search(question, k=3, where=menu_filter(theme=theme))
    for h in hits:
        print(f"  [{h['distance']:.3f}] {h['category'][:25]} | themes: {h['themes'][:40]} | {cite(h)[:60]}")
    if not hits:
        print("  (no document of this theme in the test sample)")
