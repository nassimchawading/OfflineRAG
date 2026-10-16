"""Part 5 check: run cleaning + chunking on one extracted PDF and show the result.

Run:  .venv\\Scripts\\python.exe tests\\test_chunking.py ["MR TRACTION"]
"""
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from chunking import clean_page, is_skippable, load_records, make_chunks  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
name = sys.argv[1] if len(sys.argv) > 1 else "MR TRACTION"
records = load_records(ROOT / "data" / "extracted" / f"{name}.jsonl")

cleaned = [clean_page(r["text"]) for r in records]
skipped = [r["page"] for r, (c, _) in zip(records, cleaned) if is_skippable(c)]
no_printed = [r["page"] for r, (c, p) in zip(records, cleaned) if p is None and not is_skippable(c)]
left_footer = sum("MR2" in c for c, _ in cleaned)
print(f"pages: {len(records)}, skipped: {len(skipped)}, kept: {len(records) - len(skipped)}")
print(f"skipped pages (first 40): {skipped[:40]}")
print(f"kept pages with no printed page number found: {len(no_printed)} {no_printed[:15]}")
print(f"pages still containing 'MR2' after cleaning: {left_footer}")

chunks = make_chunks(records)
sizes = [len(c["text"]) for c in chunks]
print(f"\nchunks: {len(chunks)}, size min {min(sizes)}, median {statistics.median(sizes):.0f}, max {max(sizes)} chars")
print(f"chunks over 1500 chars: {sum(s > 1500 for s in sizes)}")

for c in chunks:
    if c["page_start"] <= 100 <= c["page_end"]:
        print(f"\n----- chunk {c['id']}: PDF p.{c['page_start']}-{c['page_end']}, "
              f"printed {c['printed_start']}-{c['printed_end']}, {len(c['text'])} chars -----")
        print(c["text"])
        break
