"""Part 5 (updated in Part 7b): find the chunks closest in meaning to a question, optionally inside one menu.

Run (Ollama must be running):  .venv\\Scripts\\python.exe src\\search.py "your question"
"""
import sys

from index import embed, get_collection
from taxonomy import theme_key


def menu_filter(category: str = "", subcategory: str = "", source: str = "", theme: str = "") -> dict | None:
    """ChromaDB 'where' filter for a menu of the app (labels as in data/catalog.csv); None = everything.
    theme: a cross-domain theme of taxonomy.THEMES (e.g. "Capteurs"), whatever the category."""
    parts = [{k: v} for k, v in (("category", category), ("subcategory", subcategory), ("source", source)) if v]
    if theme:
        parts.append({theme_key(theme): True})
    if not parts:
        return None
    return parts[0] if len(parts) == 1 else {"$and": parts}


def search(question: str, k: int = 5, where: dict | None = None) -> list[dict]:
    """Return the k most relevant chunks, best first, each with its text, metadata and distance."""
    res = get_collection().query(query_embeddings=embed([question], on_gpu=False), n_results=k, where=where)
    return [{"id": i, "text": t, "distance": d, **m}
            for i, t, d, m in zip(res["ids"][0], res["documents"][0], res["distances"][0], res["metadatas"][0])]


def cite(hit: dict) -> str:
    """Human-readable source, e.g. 'Performance des processeurs et des systèmes (TI H2546), PDF p. 3-4'."""
    first, last = hit["printed_start"] or hit["printed_end"], hit["printed_end"] or hit["printed_start"]
    printed = first + (f" to {last}" if last != first else "")
    pdf = f"{hit['page_start']}" + (f"-{hit['page_end']}" if hit["page_end"] != hit["page_start"] else "")
    name = hit.get("title") or hit["book"]
    if hit.get("ti_code"):
        name += f" (TI {hit['ti_code']})"
    return f"{name}, p. {printed} (PDF p. {pdf})" if printed else f"{name}, PDF p. {pdf}"


if __name__ == "__main__":
    for hit in search(" ".join(sys.argv[1:])):
        print(f"[{hit['distance']:.3f}] {cite(hit)}  [{hit.get('category', '')}]\n    {hit['text'][:200]!r}\n")
