"""Part 4 check: inspect the extracted text of one PDF to judge its quality.

Run:  .venv\\Scripts\\python.exe tests\\inspect_extraction.py ["MR TRACTION"]
"""
from collections import Counter
from pathlib import Path
import json
import statistics
import sys

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
name = sys.argv[1] if len(sys.argv) > 1 else "MR TRACTION"
records = [json.loads(line) for line in open(ROOT / "data" / "extracted" / f"{name}.jsonl", encoding="utf-8")]
chars = [r["n_chars"] for r in records]

print(f"=== {name}: {len(records)} pages ===")
print("\n1. Characters per page")
q = statistics.quantiles(chars, n=10) if len(chars) > 1 else [chars[0]]
print(f"   min {min(chars)}, 10% {q[0]:.0f}, median {statistics.median(chars):.0f}, 90% {q[-1]:.0f}, max {max(chars)}")
for lo, hi in [(0, 50), (50, 300), (300, 1000), (1000, 2000), (2000, 10**9)]:
    n = sum(lo <= c < hi for c in chars)
    print(f"   {lo:>5}-{hi if hi < 10**9 else '...':<5} chars: {n:>5} pages")

print("\n2. Near-empty pages (<50 chars): how much of the page is covered by one image?")
print("   (big image + no text = probably a scanned page that would need OCR)")
empty = [r for r in records if r["n_chars"] < 50]
with pymupdf.open(ROOT / "data" / "pdfs" / f"{name}.pdf") as doc:
    scan_like = 0
    for r in empty:
        page = doc[r["page"] - 1]
        page_area = abs(page.rect)
        biggest = max((abs(pymupdf.Rect(i["bbox"]) & page.rect) / page_area for i in page.get_image_info()), default=0)
        n_drawings = len(page.get_drawings())
        if biggest > 0.6:
            scan_like += 1
        print(f"   p.{r['page']:>4}: {r['n_chars']:>2} chars, {r['n_images']} images, "
              f"biggest image covers {biggest:.0%}, {n_drawings} vector drawings | {r['text'][:40]!r}")
    print(f"   -> {scan_like} of {len(empty)} look like full-page images")

print("\n3. Repeated first/last lines (headers/footers), top 8 each")
firsts = Counter(r["text"].splitlines()[0].strip() for r in records if r["text"])
lasts = Counter(r["text"].splitlines()[-1].strip() for r in records if r["text"])
for label, counter in (("first", firsts), ("last", lasts)):
    for line, n in counter.most_common(8):
        if n > 3:
            print(f"   {label} line on {n:>4} pages: {line[:70]!r}")

print("\n4. Sample pages")
by_chars = sorted(records, key=lambda r: r["n_chars"])
samples = {"median page": by_chars[len(by_chars) // 2], "fullest page": by_chars[-1], "page 100": records[min(99, len(records) - 1)]}
for label, r in samples.items():
    print(f"\n----- {label}: p.{r['page']} ({r['n_chars']} chars, {r['n_images']} images) -----")
    print(r["text"][:1200])
