"""Part 11: personalised explanations and summaries, on top of the RAG search of ask.py.

explain(question, level, where)  explanation for a level (débutant / étudiant / ingénieur), from the
                                 passages found, with sources [n]
synthesise(subject, where)       synthesis of what the documents say about a subject (several documents)
summarise_document(row)          summary of one whole document (TI article or book) in two passes:
                                 each part by the fast model, then the summary of the parts by the strong
                                 model. Works from data/extracted (no need to be indexed). Saved in
                                 data/summaries/: asking again is instant.
find_documents(words)            catalogue documents whose title contains these words

Models: see llm.py (default: "fort" = qwen3:8b for explanations and summaries).
"""
from pathlib import Path
import time

import ollama

import llm
from ask import NOT_FOUND, generate, retrieve
from catalog import load_catalog
from chunking import load_records, make_chunks
from extract import jsonl_path
from taxonomy import norm

ROOT = Path(__file__).resolve().parent.parent
SUMMARY_DIR = ROOT / "data" / "summaries"
BIG_CTX = 6144          # the strong model reads more passages: a little more context (more of it on the CPU)

LEVELS = {
    "débutant": "un débutant complet : pas de jargon (ou expliqué avec des mots simples), une analogie de la vie "
                "courante, des étapes courtes.",
    "étudiant": "un étudiant en école d'ingénieur : définitions précises, rôle de chaque grandeur, formules "
                "expliquées si les extraits en donnent, un exemple.",
    "ingénieur": "un ingénieur du domaine : réponse concise et technique, hypothèses, ordres de grandeur et "
                 "limites donnés par les extraits.",
}
LEVEL_ALIASES = {norm(k): k for k in LEVELS} | {"debut": "débutant", "etu": "étudiant", "ing": "ingénieur",
                                                "expert": "ingénieur", "beginner": "débutant",
                                                "student": "étudiant", "engineer": "ingénieur"}

EXPLAIN_SYSTEM = """Tu es un enseignant qui explique des notions techniques à partir d'une bibliothèque de
documents d'ingénierie (Techniques de l'Ingénieur, livres techniques).
Public : {level}
Règles :
- Les FAITS techniques (définitions, valeurs, fonctionnement) viennent UNIQUEMENT des extraits numérotés ;
  cite-les entre crochets, par exemple [1] ou [2][3].
- Tu peux ajouter une analogie ou un exemple pour aider à comprendre, mais annonce-les comme tels
  ("Analogie : ...") et n'y ajoute aucun fait technique nouveau.
- Vérifie que ton explication ne se contredit pas et dit exactement ce que disent les extraits
  (ni plus général, ni plus restreint).
- Si les extraits ne suffisent pas pour expliquer la notion, dis ce qui manque.
- Structure : 1) l'idée en une phrase, 2) l'explication, 3) "À retenir" en 2 ou 3 points.
- Écris les formules en LaTeX entre $ et $.
- Réponds dans la langue de la question."""

SYNTHESIS_SYSTEM = """Tu fais la synthèse de ce que disent des extraits de documents d'ingénierie sur un sujet.
Règles :
- Uniquement à partir des extraits numérotés ; cite-les entre crochets, par exemple [1] ou [2][3].
- Regroupe par idées (pas extrait par extrait). Signale les points où les extraits divergent.
- Structure : un titre, les points clés en liste, les valeurs ou chiffres importants avec leurs conditions,
  puis "Limites" : ce que les extraits ne couvrent pas.
- Écris les formules en LaTeX entre $ et $.
- Ne te contredis pas. Réponds dans la langue du sujet."""

PART_SYSTEM = """Résume cette partie d'un document technique en 3 à 5 points très courts (80 mots au total).
Garde les définitions, les valeurs numériques avec leurs unités et conditions, les noms de méthodes et de
normes. N'invente rien, pas d'introduction ni de conclusion. Réponds en français."""

FINAL_SYSTEM = """Voici les résumés successifs des parties du document « {title} » ({pages} pages).
Chaque partie commence par ses pages, par exemple "Partie 3 (p. 4-5)".
Rédige le résumé du document entier, uniquement à partir de ces résumés :
1) De quoi parle le document (2 ou 3 phrases).
2) Les idées principales : 6 à 8 points AU MAXIMUM, chacun avec les pages de la partie d'où il vient,
   par exemple (p. 4-5). N'utilise que les pages indiquées dans les titres des parties.
3) Les valeurs et chiffres clés (5 au maximum), avec leurs conditions.
4) À qui ce document est utile (1 phrase).
350 mots maximum. Formules en LaTeX entre $ et $. Ne te contredis pas. Réponds en français."""

PART_CHARS = 6000       # text per part (~1 700 tokens): fits the 4 096-token context of the fast model
FINAL_CHARS = 12000     # part summaries given at once to the strong model (~3 400 tokens + answer < BIG_CTX)
SEC_PER_PART = 25       # measured on H2546 (fast model, 13 parts), used for the time estimate
SEC_FINAL = 150         # strong model: ~10 s load + reading + ~450 tokens at ~4 tokens/s


def level_of(text: str) -> str:
    return LEVEL_ALIASES.get(norm(text), "")


def explain(question: str, level: str = "étudiant", where: dict | None = None, on_token=None) -> dict:
    result = retrieve(question, where)
    result["level"] = level
    if not result["sources"]:
        result["answer"] = NOT_FOUND[result["lang"]]
        return result
    return generate("explication", EXPLAIN_SYSTEM.format(level=LEVELS[level]), result, label="NOTION À EXPLIQUER",
                    num_ctx=BIG_CTX, on_token=on_token)


def synthesise(subject: str, where: dict | None = None, on_token=None) -> dict:
    result = retrieve(subject, where, k=6)
    if not result["sources"]:
        result["answer"] = NOT_FOUND[result["lang"]]
        return result
    return generate("synthese", SYNTHESIS_SYSTEM, result, label="SUJET", num_ctx=BIG_CTX, on_token=on_token)


def find_documents(words: str, limit: int = 10) -> list[dict]:
    """Extracted documents whose title (or path) contains all these words, shortest titles first."""
    wanted = norm(words).split()
    found = [r for r in load_catalog()
             if r["status"] in ("ok", "scan") and all(w in norm(r["title"] + " " + r["path"]) for w in wanted)]
    found = [r for r in found if jsonl_path(r["path"]).exists()]
    return sorted(found, key=lambda r: len(r["title"]))[:limit]


def _parts(row: dict) -> list[dict]:
    """The cleaned chunks of a document, grouped into parts of about PART_CHARS characters."""
    parts, current = [], []
    for c in make_chunks(load_records(jsonl_path(row["path"]))):
        if current and sum(len(x["text"]) for x in current) + len(c["text"]) > PART_CHARS:
            parts.append(current)
            current = []
        current.append(c)
    if current:
        parts.append(current)
    return [{"text": "\n".join(c["text"] for c in p), "page_start": p[0]["page_start"], "page_end": p[-1]["page_end"]}
            for p in parts]


def summary_plan(row: dict) -> dict:
    """How long a summary will take (to warn before summarising a 500-page book)."""
    n = len(_parts(row))
    return {"parts": n, "seconds": n * SEC_PER_PART + SEC_FINAL, "cached": summary_path(row).exists()}


def summary_path(row: dict) -> Path:
    return SUMMARY_DIR / (jsonl_path(row["path"]).stem + ".md")


def summarise_part(text: str) -> str:
    """Summary of one part by the fast model. Tables of numbers use many more tokens than words: if the part
    is still too long for the context window, split it in two halves and summarise each one."""
    try:
        return llm.chat("resume_partie", [{"role": "system", "content": PART_SYSTEM},
                                          {"role": "user", "content": text}], num_ctx=BIG_CTX, temperature=0.1)["text"]
    except ollama.ResponseError as e:
        if "exceed" not in str(e) or len(text) < 500:
            raise
        lines = text.splitlines()
        half = len(lines) // 2 if len(lines) > 1 else 0
        first, second = ("\n".join(lines[:half]), "\n".join(lines[half:])) if half else (text[:len(text) // 2],
                                                                                           text[len(text) // 2:])
        return summarise_part(first) + "\n" + summarise_part(second)


def summarise_document(row: dict, on_token=None, on_progress=None, refresh: bool = False) -> dict:
    """Summary of a whole document. on_progress(text) reports the first pass (one call per part)."""
    path = summary_path(row)
    if path.exists() and not refresh:
        return {"answer": path.read_text(encoding="utf-8").split("\n---\n", 1)[-1].strip(), "cached": True,
                "document": row, "seconds": 0.0}
    start = time.time()
    parts = _parts(row)
    notes = []  # (first page, last page, summary)
    for i, part in enumerate(parts, 1):
        if on_progress:
            on_progress(f"partie {i}/{len(parts)} (p. {part['page_start']}-{part['page_end']})")
        notes.append((part["page_start"], part["page_end"], summarise_part(part["text"])))

    def labelled(ns):
        return [f"Partie {i} (p. {a}-{b}) :\n{text}" for i, (a, b, text) in enumerate(ns, 1)]

    # very long documents (books): summarise groups of part summaries again until they fit in one prompt.
    # Each group keeps the page range of its parts, so the final summary can still cite real pages.
    while sum(len(n) for n in labelled(notes)) > FINAL_CHARS:
        groups, current = [], []
        for n in notes:
            if current and sum(len(x[2]) for x in current) + len(n[2]) > PART_CHARS:
                groups.append(current)
                current = []
            current.append(n)
        groups.append(current)
        if on_progress:
            on_progress(f"regroupement de {len(notes)} résumés en {len(groups)}")
        notes = [(g[0][0], g[-1][1], summarise_part("\n\n".join(labelled(g)))) for g in groups]
    if on_progress:
        on_progress(f"résumé final avec {llm.model_for('resume')}")
    reply = llm.chat("resume", [{"role": "system", "content": FINAL_SYSTEM.format(title=row["title"], pages=row["pages"])},
                                {"role": "user", "content": "\n\n".join(labelled(notes))}],
                     num_ctx=BIG_CTX, temperature=0.2, on_token=on_token)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    header = (f"# {row['title']}\n\nDocument : {row['path']}\nRésumé fait avec {llm.model_for('resume_partie')} "
              f"(parties) + {reply['model']} (final), {len(parts)} parties, {time.time() - start:.0f} s\n")
    path.write_text(f"{header}\n---\n{reply['text']}\n", encoding="utf-8")
    return {"answer": reply["text"], "cached": False, "document": row, "parts": len(parts),
            "seconds": time.time() - start, "model": reply["model"], "tokens_per_s": reply["tokens_per_s"]}
