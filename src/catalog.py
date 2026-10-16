"""Part 7b: catalogue of every file in data/pdfs -> data/catalog.csv (opens in Excel).

One row per file: path, status, source, category, subcategory, ti_code, title, pages, size_mb, duplicate_of.
status:  ok         readable PDF, will be indexed
         scan       no text layer (scanned book): needs OCR before it can be indexed
         duplicate  same content as another file (same bytes, or same TI article code + same length)
         empty      cannot be opened (zero-filled or damaged file)
         not_pdf    .swf, .exe, .rar, .djvu... the pipeline only reads PDFs
Categories come from src/taxonomy.py. To correct one document, add a line to data/catalog_overrides.csv:
    path;category;subcategory;title;themes   (path and labels as in catalog.csv, empty = keep;
                                              themes separated by " | ", as in catalog.csv)

Slow facts (hash, pages, title, TI code, scan check) are cached in data/catalog_cache.json, so a re-run
after adding PDFs only reads the new files.

Run:  .venv\\Scripts\\python.exe src\\catalog.py           build / refresh the catalogue
      .venv\\Scripts\\python.exe src\\catalog.py --clean   also MOVE duplicate, empty and not_pdf files to
                                                       data/_retires/<status>/... (nothing is deleted)
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import hashlib
import json
import re
import shutil
import sys
import unicodedata

import pymupdf

from taxonomy import (CATEGORIES, GENERAL, THEMES, SOURCE_BOOKS, SOURCE_MISC, SOURCE_TI, code_category, folder_category,
                      folder_subcategory, norm, subcategory, themes, title_category)

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"
CATALOG = ROOT / "data" / "catalog.csv"
CACHE = ROOT / "data" / "catalog_cache.json"
OVERRIDES = ROOT / "data" / "catalog_overrides.csv"
RETIRED_DIR = ROOT / "data" / "_retires"
KEEP_FILES = {"PUT_PDFS_HERE.txt"}
FACTS_VERSION = 4  # bump when read_facts() changes, to refresh the cache
FIELDS = ["path", "status", "source", "category", "subcategory", "themes", "ti_code", "title", "pages", "size_mb", "duplicate_of", "sha1"]

pymupdf.TOOLS.mupdf_display_errors(False)  # damaged PDFs print many harmless MuPDF warnings

# "Titre (H2546).pdf"  |  "H2546.PDF", "R1810B.pdf", "H2768(1).PDF"
NAME_PAREN_RE = re.compile(r"\(([A-Z]{1,4}) ?(\d{2,5})\)")
NAME_ONLY_RE = re.compile(r"([A-Z]{1,4}) ?(\d{2,5})[A-Z]?(?:\s?\(\d\))?")
# page footer "H 2 546 − 3" / "AG 4 220 – 2", or "Référence : H2546"
FOOTER_RE = re.compile(r"(?<![A-Za-z])([A-Z]{1,3}) ?(\d(?: ?\d){2,4}) ?[−–-] ?\d{1,3}(?!\d)")
REF_RE = re.compile(r"(?:R[ée]f[ée]rence|r[ée]f\.)\s*(?:Internet)?\s*:?\s*([A-Z]{1,4}) ?(\d{3,5})", re.I)
TI_RE = re.compile(r"Techniques de l.Ing[ée]nieur", re.I)
# names that are not titles: "H2546", "af3520doc", "A120DOC", "R1810B", "H2768(1)"
CODE_LIKE_RE = re.compile(r"[A-Za-z]{1,4} ?\d{2,5}[A-Za-z]{0,5}(?:\s?\(\d\))?")


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def big_font_title(page) -> str:
    """Title of a TI article = the biggest text on page 1 (e.g. 'Machines asynchrones - Régime permanent')."""
    spans = [(round(s["size"]), s["text"].strip()) for b in page.get_text("dict")["blocks"] for l in b.get("lines", [])
             for s in l["spans"] if len(s["text"].strip()) > 1]
    for size in sorted({size for size, _ in spans}, reverse=True)[:3]:
        text = " - ".join(t for sz, t in spans if sz == size)
        # a real title has at least two words; skips internal ids like "af3333doc" or "A120DOC"
        if size >= 12 and re.search(r"\w{3,}\W+\w+", text):
            return unicodedata.normalize("NFKC", text)[:150]
    return ""


def read_facts(path: Path, sha1: str | None = None) -> dict:
    """Everything slow to compute about one file (cached)."""
    facts = {"v": FACTS_VERSION, "size": path.stat().st_size, "mtime": path.stat().st_mtime, "sha1": sha1 or sha1_of(path)}
    if path.suffix.lower() != ".pdf":
        return facts | {"kind": "not_pdf"}
    try:
        doc = pymupdf.open(path)
    except Exception:
        return facts | {"kind": "empty"}
    with doc:
        if doc.needs_pass or doc.page_count == 0:
            return facts | {"kind": "empty"}
        n = doc.page_count
        first = "\n".join(doc[i].get_text() for i in range(min(3, n)))
        sample = sorted({round(i * (n - 1) / 7) for i in range(8)})
        # a page is unusable if it has (almost) no text, or garbage text from a broken font encoding
        # ('!"# $%&'(' instead of words): both need OCR
        textless = sum(not good_text(doc[i].get_text()) for i in sample)
        footer = Counter(m.group(1) + m.group(2).replace(" ", "") for m in FOOTER_RE.finditer(first))
        ref = REF_RE.search(first)
        text_code, sure = None, False
        if ref:
            text_code, sure = ref.group(1).upper() + ref.group(2), True
        elif footer:
            text_code, count = footer.most_common(1)[0]
            sure = count >= 2
        return facts | {"kind": "pdf", "pages": n, "scan": textless >= 0.7 * len(sample), "ti_text": bool(TI_RE.search(first)),
                        "text_code": text_code, "text_code_sure": sure, "pdf_title": big_font_title(doc[0]),
                        "meta_title": meta_title(doc.metadata or {})}


def good_text(text: str) -> bool:
    """Enough text, and mostly letters/digits. Broken font encodings and bad OCR layers give punctuation soup
    ('!"# $%&', '\\s È : x : " t'). Dotted leaders and rule lines of tables ('.....', '____') are ignored."""
    chars = [c for c in re.sub(r"[._\-−–]{3,}", "", text) if not c.isspace()]
    return len(chars) >= 100 and sum(c.isalnum() for c in chars) / len(chars) >= 0.6


def meta_title(meta: dict) -> str:
    """Title stored in the PDF properties, if it looks like a real title (not a file name or a default)."""
    title = unicodedata.normalize("NFKC", (meta.get("title") or "").strip())
    if (len(title) < 4 or not re.search(r"[a-zA-Z]{3,}\W+\w", title) or re.search(r"\.(pdf|doc|fm|mif)\b|[\\/]", title, re.I)
            or re.match(r"(untitled|microsoft|document)", title, re.I)):
        return ""
    return title.replace("E'lectronique", "Électronique").replace(" a' ", " à ")[:150]


def ti_code(path: Path, facts: dict) -> tuple[str | None, bool]:
    """(code, sure). The file name wins over the text: the text can quote other references."""
    m = NAME_PAREN_RE.search(path.name)
    if m:
        return m.group(1) + m.group(2), True
    m = NAME_ONLY_RE.fullmatch(path.stem.strip())
    if m:
        return m.group(1) + m.group(2), True
    return facts.get("text_code"), facts.get("text_code_sure", False)


def name_title(path: Path) -> str:
    """Title written in the file name, '' if the name is only a code, an id or an ISBN."""
    if CODE_LIKE_RE.fullmatch(path.stem.strip()):
        return ""
    title = NAME_PAREN_RE.sub("", path.stem).replace("_", " ").replace("&#233;", "é")
    title = re.sub(r"^\d{7,10}X?[\s-]*", "", title)            # ISBN / id prefix: "2100540173Froid"
    title = re.sub(r"ebooksclub\.org\s*|\s*by playm.*$|www\.\S+", "", title, flags=re.I)  # download-site tags
    title = re.sub(r"(?<=[a-z])(?=[A-Z][a-z])", " ", title)   # "GestionDesStocks" -> "Gestion Des Stocks"
    title = re.sub(r"\s{2,}", " ", unicodedata.normalize("NFKC", title)).strip(" -.")
    return title if len(title) >= 3 else ""


def nice_title(path: Path, facts: dict) -> str:
    return name_title(path) or facts.get("pdf_title") or facts.get("meta_title") or path.stem


def classify(rel: Path, facts: dict) -> dict:
    parts = list(rel.parent.parts)
    top = parts[0] if parts else ""
    code, sure = ti_code(rel, facts)
    title = nice_title(rel, facts)
    misc = top == "Books" and "CV LETTRE" in str(rel) or rel.name.startswith("L0152235_AR07")
    if misc:
        source = SOURCE_MISC
    elif top.startswith("les techniques") or (not parts and facts.get("ti_text")):
        source = SOURCE_TI
    else:
        source = SOURCE_BOOKS
    cat = "DIVERS" if misc else None
    if cat is None and source == SOURCE_TI:
        cat = title_category(code_category(code), title, code)
    if cat is None:
        cat = folder_category(parts) or folder_category([title]) or folder_category([rel.stem])
    sub = GENERAL
    if cat:
        sub = folder_subcategory(parts) or subcategory(cat, norm(title))
        if sub == GENERAL:
            generic = {"books", "ebook", "cd1", "cd2", "cd3", "cd4", "cd5", "cd6", "cd 3"}
            folders = " ".join(p for p in map(norm, parts) if p not in generic and not p.startswith("les techniques"))
            sub = subcategory(cat, folders + " " + norm(rel.stem))
    return {"source": source, "category": CATEGORIES[cat][0] if cat else "?", "subcategory": sub,
            "ti_code": code or "", "code_sure": sure, "title": title}


def canonical_key(row: dict) -> tuple:
    """Which copy to keep among duplicates: inside the folder tree, descriptive name, deepest folder."""
    rel = Path(row["path"])
    return (len(rel.parts) > 1, bool(name_title(rel)), len(rel.parts), -len(row["path"]))


def build() -> list[dict]:
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    rows, new_cache = [], {}
    files = sorted(p for p in PDF_DIR.rglob("*") if p.is_file() and p.name not in KEEP_FILES)
    for i, path in enumerate(files, 1):
        rel = path.relative_to(PDF_DIR)
        key = str(rel)
        stat = path.stat()
        facts = cache.get(key)
        if not facts or facts["size"] != stat.st_size or facts["mtime"] != stat.st_mtime:
            facts = read_facts(path)
        elif facts.get("v") != FACTS_VERSION:   # extraction rules changed: re-read, but the file itself did not
            facts = read_facts(path, facts["sha1"])
        new_cache[key] = facts
        if i % 250 == 0:
            print(f"  {i}/{len(files)} files read", flush=True)
            CACHE.write_text(json.dumps(new_cache, ensure_ascii=False), encoding="utf-8")  # resumable
        row = {"path": key, "sha1": facts["sha1"], "size_mb": round(facts["size"] / 1e6, 1),
               "pages": facts.get("pages", ""), "duplicate_of": ""}
        row |= classify(rel, facts)
        row["status"] = facts["kind"] if facts["kind"] != "pdf" else ("scan" if facts["scan"] else "ok")
        rows.append(row)
    CACHE.write_text(json.dumps(new_cache, ensure_ascii=False), encoding="utf-8")

    # 1. same bytes
    by_hash = defaultdict(list)
    for r in rows:
        if r["status"] in ("ok", "scan"):
            by_hash[r["sha1"]].append(r)
    for group in by_hash.values():
        keep = max(group, key=canonical_key)
        for r in group:
            if r is not keep:
                r["status"], r["duplicate_of"] = "duplicate", keep["path"]
    # 2. same TI article saved twice (other scan/edition): same sure code and same length
    by_code = defaultdict(list)
    for r in rows:
        if r["status"] in ("ok", "scan") and r["code_sure"] and r["ti_code"]:
            by_code[r["ti_code"]].append(r)
    for group in by_code.values():
        group.sort(key=canonical_key, reverse=True)
        for r in group[1:]:
            keep = group[0]
            if abs((r["pages"] or 0) - (keep["pages"] or 0)) <= 1:
                r["status"], r["duplicate_of"] = "duplicate", keep["path"]

    # manual corrections, then cross-domain themes (they depend on the final title and subcategory)
    fixes = {}
    if OVERRIDES.exists():
        with open(OVERRIDES, encoding="utf-8-sig", newline="") as f:
            fixes = {r["path"]: r for r in csv.DictReader(f, delimiter=";")}
    else:
        OVERRIDES.write_text("path;category;subcategory;title;themes\n", encoding="utf-8-sig")
    for r in rows:
        fix = fixes.get(r["path"], {})
        for field in ("category", "subcategory", "title"):
            r[field] = fix.get(field) or r[field]
        r["themes"] = fix.get("themes") or " | ".join(themes(r["title"], r["subcategory"]))
    return rows


def load_catalog() -> list[dict]:
    with open(CATALOG, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=";"))


def write_csv(rows: list[dict], path: Path) -> None:
    # utf-8-sig + ";" : opens directly in French Excel with accents right
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def clean(rows: list[dict]) -> None:
    """Move duplicate / empty / not_pdf files out of data/pdfs (into data/_retires), keep a list of them."""
    moved = [r for r in rows if r["status"] in ("duplicate", "empty", "not_pdf")]
    for r in moved:
        src = PDF_DIR / r["path"]
        dst = RETIRED_DIR / r["status"] / r["path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    log = RETIRED_DIR / "retires.csv"
    old = []
    if log.exists():
        with open(log, encoding="utf-8-sig", newline="") as f:
            old = list(csv.DictReader(f, delimiter=";"))
    write_csv(old + moved, log)
    # remove the folders left empty
    for d in sorted((p for p in PDF_DIR.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        if not any(d.iterdir()):
            d.rmdir()
    print(f"moved {len(moved)} files ({sum(r['size_mb'] for r in moved):,.0f} MB) to {RETIRED_DIR.relative_to(ROOT)}"
          f" (list: {log.relative_to(ROOT)})")


def report(rows: list[dict]) -> None:
    st = Counter(r["status"] for r in rows)
    print(f"\n{len(rows)} files: " + ", ".join(f"{k} {v}" for k, v in st.most_common()))
    kept = [r for r in rows if r["status"] in ("ok", "scan")]
    print(f"documents kept: {len(kept)} ({sum(r['pages'] or 0 for r in kept):,} pages), "
          f"of which scan (OCR needed): {st['scan']}")
    print("by source: " + ", ".join(f"{k} {v}" for k, v in Counter(r["source"] for r in kept).most_common()))
    by_cat = defaultdict(Counter)
    for r in kept:
        by_cat[r["category"]][r["subcategory"]] += 1
    for cat, subs in sorted(by_cat.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"\n{cat}: {sum(subs.values())}")
        for sub, n in subs.most_common():
            print(f"    {n:4}  {sub}")
    print("\nThemes (cross-domain, a document can have several):")
    for theme in THEMES:
        docs = [r for r in kept if theme in r["themes"].split(" | ")]
        print(f"    {len(docs):4}  {theme}  (in {len({r['category'] for r in docs})} categories)")


def main() -> None:
    print(f"reading {PDF_DIR.relative_to(ROOT)} (first run: a few minutes, then only new files)")
    rows = build()
    if "--clean" in sys.argv[1:]:
        clean(rows)
        rows = build()
    write_csv(rows, CATALOG)
    report(rows)
    print(f"\ncatalogue: {CATALOG.relative_to(ROOT)}  (corrections: {OVERRIDES.relative_to(ROOT)})")


if __name__ == "__main__":
    main()
