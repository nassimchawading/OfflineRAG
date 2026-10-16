"""Open a source PDF at the right page (user idea 2026-10-14: read the original, not only the answer).

Microsoft Edge (installed on every Windows PC, and the default PDF viewer on this laptop) opens a local
PDF at a given page with "file:///...pdf#page=12". If Edge is not found, the PDF opens in the default
viewer at page 1. Used by ask.py (/ouvrir n) and later by the app (a button per source).
"""
from pathlib import Path
import os
import subprocess

PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "pdfs"
EDGE_PATHS = [Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
              Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe"]


def pdf_exists(hit: dict) -> bool:
    """False in a copy of the project made without data/pdfs (kit for another PC): no preview, no "open"."""
    return (PDF_DIR / hit["book"]).exists()


def page_png(book: str, page: int, dpi: int = 90) -> bytes | None:
    """Image (PNG) of one PDF page, to preview a source in the app. None if the PDF or the page is missing."""
    import pymupdf
    pdf = PDF_DIR / book
    if not pdf.exists():
        return None
    with pymupdf.open(pdf) as doc:
        if not 1 <= page <= doc.page_count:
            return None
        return doc[page - 1].get_pixmap(dpi=dpi).tobytes("png")


def source_url(hit: dict) -> str:
    """file:// address of the source PDF, at the first page of the passage."""
    return (PDF_DIR / hit["book"]).as_uri() + f"#page={hit['page_start']}"


def open_source(hit: dict) -> str:
    """Open the PDF of a search hit at its page. Returns a short message for the user."""
    pdf = PDF_DIR / hit["book"]
    if not pdf.exists():
        return f"PDF introuvable : {pdf}"
    edge = next((p for p in EDGE_PATHS if p.exists()), None)
    if edge:
        subprocess.Popen([str(edge), source_url(hit)])
        return f"ouvert dans Edge à la page {hit['page_start']} : {pdf.name}"
    os.startfile(pdf)  # default PDF viewer, page 1 (page numbers are not supported this way)
    return f"ouvert (page 1, aller à la page {hit['page_start']}) : {pdf.name}"
