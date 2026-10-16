"""Part 6: answer a question from the indexed PDFs (RAG) on the command line.

Steps: (English question -> translate to French for the search) -> search the vector database
-> keep relevant passages -> the chat model answers ONLY from those passages, citing them.

Run (Ollama must be running):
    .venv\\Scripts\\python.exe src\\ask.py "Quelle est la ... ?"     one question
    .venv\\Scripts\\python.exe src\\ask.py                           interactive: choose a menu (category),
                                                                    then questions (empty line = quit)
"""
import re
import sys
import time

import ollama

import llm
from search import cite, menu_filter, search
from taxonomy import CATEGORIES, SOURCE_TI, THEMES

NUM_CTX = 4096         # tokens the chat model can read at once (prompt + answer)
TOP_K = 4               # passages given to the model
MAX_DISTANCE = 0.55     # passages less similar than this are ignored (Part 5: off-topic >= 0.6)

SYSTEM_PROMPT = """Tu es un assistant technique pour une bibliothèque de documents d'ingénierie
(articles des Techniques de l'Ingénieur, livres techniques).
Règles :
- Réponds UNIQUEMENT à partir des extraits numérotés fournis. N'utilise pas tes connaissances générales.
- Après chaque information, cite l'extrait utilisé entre crochets, par exemple [1] ou [2][3].
- Si les extraits ne contiennent pas la réponse, dis-le clairement et ne devine pas.
- Si les extraits donnent plusieurs valeurs selon les cas (types de pièces, tableaux, conditions),
  donne TOUTES les valeurs avec leur condition et leur source, ne choisis pas une seule valeur.
- Réponds dans la langue de la question (français ou anglais), de façon claire et concise.
- Les formules et tableaux des extraits peuvent être mal mis en forme : interprète-les avec prudence.
- Écris les formules en LaTeX entre $ et $, par exemple $f = \\frac{5qL^4}{384EI}$."""

NOT_FOUND = {
    "fr": "Je n'ai pas trouvé cette information dans les documents indexés.",
    "en": "I could not find this information in the indexed documents.",
}

_EN_WORDS = {"the", "what", "how", "is", "are", "of", "for", "which", "does", "do", "an", "to", "and",
             "why", "when", "where", "can", "should", "with", "screw", "torque"}
_FR_WORDS = {"le", "la", "les", "des", "du", "un", "une", "est", "quel", "quelle", "quels", "quelles",
             "comment", "pour", "et", "de", "que", "qui", "sur", "dans", "avec", "pourquoi", "où"}


def detect_language(question: str) -> str:
    """Very simple French/English guess from common words and accents."""
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", question.lower())
    fr = sum(w in _FR_WORDS for w in words) + 2 * bool(re.search(r"[àâçéèêëîïôûùüœ]", question.lower()))
    en = sum(w in _EN_WORDS for w in words)
    return "en" if en > fr else "fr"


def translate_to_french(question: str) -> str:
    reply = llm.chat("traduction", [{"role": "user", "content":
                     "Traduis cette question technique en français. Réponds uniquement par la traduction, "
                     f"sans explication.\n\nQuestion : {question}"}], temperature=0)
    return reply["text"]


def build_prompt(question: str, hits: list[dict], label: str = "QUESTION") -> str:
    extracts = "\n\n".join(f"[{i}] Source : {cite(h)}\n{h['text']}" for i, h in enumerate(hits, 1))
    return f"EXTRAITS :\n\n{extracts}\n\n{label} : {question}"


def retrieve(question: str, where: dict | None = None, k: int = TOP_K) -> dict:
    """Search step shared by all modes: language, French search query, relevant passages, timings."""
    t, start = {}, time.time()
    lang = detect_language(question)
    search_query = translate_to_french(question) if lang == "en" else question
    t["translate"] = time.time() - start
    start = time.time()
    hits = [h for h in search(search_query, k=k, where=where) if h["distance"] <= MAX_DISTANCE]
    t["search"] = time.time() - start
    return {"question": question, "lang": lang, "search_query": search_query, "sources": hits, "timings": t}


def generate(mode: str, system: str, result: dict, label: str = "QUESTION", num_ctx: int = NUM_CTX,
             on_token=None) -> dict:
    """Ask the model of `mode` to answer from result["sources"]; fills result. If the passages are too long
    for the context window (tables of numbers use many tokens), drop the least relevant one and retry."""
    hits = result["sources"]
    while True:
        try:
            reply = llm.chat(mode, [{"role": "system", "content": system},
                                    {"role": "user", "content": build_prompt(result["question"], hits, label)}],
                             num_ctx=num_ctx, on_token=on_token)
            break
        except ollama.ResponseError as e:
            if "exceed" not in str(e) or len(hits) == 1:
                raise
            hits = hits[:-1]
    result["sources"] = hits
    reply["text"], result["bad_citations"] = check_citations(reply["text"], len(hits))
    result["timings"]["answer_total"] = reply["seconds"]
    result["timings"]["model_load"] = reply["load_s"]
    result.update(answer=reply["text"], model=reply["model"], num_ctx=num_ctx, prompt_tokens=reply["prompt_tokens"],
                  answer_tokens=reply["answer_tokens"], tokens_per_s=reply["tokens_per_s"])
    return result


def check_citations(text: str, n_sources: int) -> tuple[str, list[int]]:
    """Remove citations like [8] that point to no passage (the model invented them); return the removed numbers.
    Kept: [1]..[n_sources]. The streamed text already shown is not changed; the returned text is clean."""
    bad = sorted({int(m) for m in re.findall(r"\[(\d+)\]", text) if not 1 <= int(m) <= n_sources})
    for b in bad:
        text = text.replace(f"[{b}]", "")
    return text, bad


def print_token(text: str) -> None:
    print(text, end="", flush=True)


def answer(question: str, stream: bool = True, where: dict | None = None) -> dict:
    """Run the full RAG pipeline. Returns answer text, sources, timings and token counts.
    where: search only inside one menu (see search.menu_filter), None = all documents."""
    result = retrieve(question, where)
    if not result["sources"]:
        result["answer"] = NOT_FOUND[result["lang"]]
        if stream:
            print(result["answer"])
        return result
    generate("question", SYSTEM_PROMPT, result, on_token=print_token if stream else None)
    if stream:
        print()
    return result


last_sources: list[dict] = []  # sources of the last answer, for /ouvrir n


def print_report(r: dict) -> None:
    global last_sources
    last_sources = r["sources"]
    print("\nSources:" + ("  (/ouvrir n pour lire la source à la bonne page)" if r["sources"] else ""))
    for i, h in enumerate(r["sources"], 1):
        print(f"  [{i}] {cite(h)}  (distance {h['distance']:.3f})")
    if r["lang"] == "en":
        print(f"(searched in French as: {r['search_query']!r})")
    t = r["timings"]
    line = f"(translate {t['translate']:.1f} s, search {t['search']:.1f} s"
    if "answer_total" in t:
        line += (f", answer {t['answer_total']:.1f} s with {r['model']} incl. model load {t['model_load']:.1f} s, "
                 f"{r['tokens_per_s']:.1f} tokens/s, prompt {r['prompt_tokens']}/{r['num_ctx']} tokens")
    print(line + ")")
    if r.get("bad_citations"):
        print(f"WARNING: the model cited passages that do not exist {r['bad_citations']} (removed from the saved answer)")
    if r.get("prompt_tokens", 0) + 500 > r.get("num_ctx", NUM_CTX):
        print("WARNING: prompt close to the context limit, the answer may be cut or passages truncated")


def choose_menu() -> tuple[str, dict | None]:
    """Ask which menu to search in: categories of src/taxonomy.py, Techniques de l'Ingénieur, or a theme."""
    menus = [("Tous les documents", None), (SOURCE_TI, menu_filter(source=SOURCE_TI))]
    menus += [(label, menu_filter(category=label)) for label, _ in CATEGORIES.values()]
    menus += [(f"Thème : {theme}", menu_filter(theme=theme)) for theme in THEMES]
    for i, (label, _) in enumerate(menus):
        print(f"  {i:2}  {label}")
    choice = input("Menu (number, empty = 0): ").strip()
    return menus[int(choice)] if choice.isdigit() and int(choice) < len(menus) else menus[0]


HELP = """Commandes :
  une question                      réponse normale (modèle rapide)
  /explique [niveau] question       explication adaptée : debutant, etudiant (défaut) ou ingenieur
  /synthese sujet                   synthèse de ce que disent les documents sur un sujet
  /resume mots du titre             résumé d'un document entier (article TI ou livre)
  /ouvrir n                         ouvrir la source [n] de la dernière réponse, à la bonne page
  /modele rapide | fort | auto     choisir le modèle (auto = rapide pour questions et explications,
                                    fort pour synthèses et résumés)
  /menu                             changer de menu (catégorie, thème...)
  /aide                             cette aide ; ligne vide = quitter"""


def run_command(line: str, where: dict | None) -> None:
    """The /commands of the interactive mode (modes.py holds the explanation and summary features)."""
    import modes
    import viewer
    global last_sources
    cmd, _, rest = line.partition(" ")
    rest = rest.strip()
    if cmd == "/ouvrir":
        if not rest.isdigit() or not 1 <= int(rest) <= len(last_sources):
            print(f"Donne le numéro d'une source de la dernière réponse (1 à {len(last_sources)}), ex. /ouvrir 2")
        else:
            print(viewer.open_source(last_sources[int(rest) - 1]))
    elif cmd == "/modele":
        try:
            llm.set_model(rest or "auto")
        except ValueError as e:
            print(e)
        print(f"Modèle : {llm.current_choice()} (questions : {llm.model_for('question')}, "
              f"explications et résumés : {llm.model_for('explication')})")
    elif cmd == "/explique":
        first, _, question = rest.partition(" ")
        level = modes.level_of(first)
        if not level:
            level, question = "étudiant", rest
        print(f"[explication niveau {level}, modèle {llm.model_for('explication')}]")
        r = modes.explain(question, level, where, on_token=print_token)
        print(r["answer"] if "model" not in r else "")
        print_report(r)
    elif cmd == "/synthese":
        print(f"[synthèse, modèle {llm.model_for('synthese')}]")
        r = modes.synthesise(rest, where, on_token=print_token)
        print(r["answer"] if "model" not in r else "")
        print_report(r)
    elif cmd == "/resume":
        docs = modes.find_documents(rest)
        if not docs:
            print("Aucun document trouvé avec ces mots dans le titre.")
            return
        for i, d in enumerate(docs):
            plan = modes.summary_plan(d)
            when = "déjà fait" if plan["cached"] else f"~{plan['seconds'] / 60:.0f} min"
            print(f"  {i}  {d['title'][:70]}  ({d['pages']} p., {when})")
        choice = input("Document (numéro, vide = annuler) : ").strip()
        if not choice.isdigit() or int(choice) >= len(docs):
            return
        r = modes.summarise_document(docs[int(choice)], on_token=print_token,
                                     on_progress=lambda text: print(f"  ... {text}", flush=True))
        if r["cached"]:
            print(r["answer"])
        how = "déjà enregistré" if r["cached"] else f"fait en {r['seconds']:.0f} s"
        print(f"\n(résumé {how} : {modes.summary_path(docs[int(choice)]).relative_to(modes.ROOT)})")
    else:
        print(HELP)


def main() -> None:
    if len(sys.argv) > 1:
        print_report(answer(" ".join(sys.argv[1:])))
        return
    label, where = choose_menu()
    print(f"Searching in: {label}\n{HELP}")
    while True:
        line = input("\nQuestion ou /commande (vide = quitter) : ").strip()
        if not line:
            break
        if line == "/menu":
            label, where = choose_menu()
            print(f"Searching in: {label}")
        elif line.startswith("/"):
            run_command(line, where)
        else:
            print_report(answer(line, where=where))


if __name__ == "__main__":
    main()
