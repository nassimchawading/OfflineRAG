"""Part 3 test: check that the venv libraries work.

1. PyMuPDF can open the test PDF and see whether its pages contain real text
   (or are scanned images that would need OCR).
2. The ollama library can reach the running Ollama server and get an answer.

Run (Ollama must be running):  .venv\\Scripts\\python.exe tests\\test_part3.py
"""
from pathlib import Path
import sys

import ollama
import pymupdf

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "pdfs"
CHAT_MODEL = "qwen3:4b-instruct"

print(f"Python {sys.version.split()[0]} from {sys.executable}")
print(f"PyMuPDF {pymupdf.VersionBind}")

# --- 1. PyMuPDF ---
pdf_path = next(PDF_DIR.glob("*.pdf"))
doc = pymupdf.open(pdf_path)
chars_per_page = [len(page.get_text().strip()) for page in doc]
text_pages = sum(1 for c in chars_per_page if c >= 50)  # <50 chars = probably a scan or blank page
print(f"\nPDF: {pdf_path.name}")
print(f"  pages: {doc.page_count}")
print(f"  pages with real text: {text_pages} ({text_pages / doc.page_count:.0%})")
print(f"  pages with little/no text: {doc.page_count - text_pages}")
print(f"  characters on first 5 pages: {chars_per_page[:5]}")
doc.close()

# --- 2. ollama library ---
reply = ollama.chat(
    model=CHAT_MODEL,
    messages=[{"role": "user", "content": "Reply with exactly: Python can talk to Ollama."}],
)
print(f"\nOllama ({CHAT_MODEL}) replied: {reply.message.content!r}")
print("\nPart 3 test finished OK")
