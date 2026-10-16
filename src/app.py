"""Part 8: the chat app (Streamlit), on top of the same functions as ask.py.

Run (Ollama must be running), from the project folder:
    .venv\\Scripts\\python.exe -m streamlit run src\\app.py
then open http://localhost:8501 (only reachable from this laptop, nothing is sent on the internet).

8a: chat with normal questions, answer written live, sources with their passage + "open the PDF at the page".
8b: sidebar: 4 combinable filters (source, category, sub-category, theme) with document counts, model choice,
    Ollama status.
8c: modes Question / Explication (level) / Synthèse / Résumé d'un document (modes.py).
8d: preview image of the PDF page in each source (hidden, like "open", if data/pdfs is not in this copy).
"""
from pathlib import Path
import re
import sys

import ollama
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))  # so "import ask" works when run by streamlit

import llm
import modes
import viewer
from ask import NOT_FOUND, SYSTEM_PROMPT, generate, retrieve
from catalog import load_catalog
from extract import jsonl_path
from search import cite, menu_filter
from taxonomy import CATEGORIES, SOURCE_BOOKS, SOURCE_MISC, SOURCE_TI, THEMES

st.set_page_config(page_title="Bibliothèque technique", page_icon="📚", layout="wide",
                   initial_sidebar_state="expanded")
ALL = "Tous"


@st.cache_data(ttl=300)
def searchable_docs() -> list[dict]:
    """Documents that are in the database (text or OCR'd), with the fields the filters use."""
    return [{"source": r["source"], "category": r["category"], "subcategory": r["subcategory"],
             "themes": r["themes"].split(" | ") if r["themes"] else []}
            for r in load_catalog() if r["status"] in ("ok", "scan") and jsonl_path(r["path"]).exists()]


def count(docs: list[dict], source: str, category: str, subcategory: str, theme: str) -> int:
    return sum((source == ALL or d["source"] == source) and (category == ALL or d["category"] == category)
               and (subcategory == ALL or d["subcategory"] == subcategory) and (theme == ALL or theme in d["themes"])
               for d in docs)


@st.cache_data(ttl=10)
def installed_models() -> list[str] | None:
    """Model names in Ollama, or None if Ollama is not running."""
    try:
        return [m.model for m in ollama.list().models]
    except Exception:
        return None


def sidebar() -> tuple[dict | None, str]:
    """Filters + model choice. Returns (ChromaDB filter, human-readable description of the filter)."""
    docs = searchable_docs()
    s = st.session_state

    def label(value: str, **where) -> str:
        # Counts depend only on the list's own level (never on the other filters): if the option texts changed
        # between two refreshes, Streamlit would see a "new" list and reset it to "Tous".
        return f"{value}  ({count(docs, **{'source': ALL, 'category': ALL, 'subcategory': ALL, 'theme': ALL} | where)})"

    with st.sidebar:
        st.header("🔎 Où chercher")
        st.selectbox("Source", [ALL, SOURCE_TI, SOURCE_BOOKS, SOURCE_MISC], key="f_source",
                     format_func=lambda v: label(v, source=v))
        st.selectbox("Catégorie", [ALL] + [lab for lab, _ in CATEGORIES.values()], key="f_cat",
                     format_func=lambda v: label(v, category=v))
        subs = [ALL]
        if s.f_cat != ALL:
            subs += [sub for lab, sub_rules in CATEGORIES.values() if lab == s.f_cat for sub, _ in sub_rules] + ["Général"]
        if s.get("f_sub", ALL) not in subs:   # the category changed: its old sub-category no longer applies
            s.f_sub = ALL
        st.selectbox("Sous-catégorie", subs, key="f_sub", format_func=lambda v: label(v, category=s.f_cat, subcategory=v),
                     disabled=s.f_cat == ALL, help="Choisis d'abord une catégorie")
        st.selectbox("Thème (transversal)", [ALL] + list(THEMES), key="f_theme",
                     format_func=lambda v: label(v, theme=v))
        n = count(docs, s.f_source, s.f_cat, s.f_sub, s.f_theme)
        st.caption(f"**{n} documents** dans la recherche" + (" ⚠️ très peu : élargis les filtres" if 0 < n < 5 else ""))
        if n == 0:
            st.warning("Aucun document avec ces filtres.")

        st.header("🧠 Modèle")
        models = installed_models()
        options = ["auto", "rapide"] + (["fort"] if models and any(m.startswith(llm.MODELS["fort"]) for m in models) else [])
        captions = {"auto": "rapide pour questions et explications, fort pour synthèses et résumés",
                    "rapide": f"{llm.MODELS['rapide']}, ~30 s par réponse",
                    "fort": f"{llm.MODELS['fort']}, 2 à 3 fois plus lent"}
        choice = st.radio("Modèle", options, key="f_model", label_visibility="collapsed",
                          captions=[captions[o] for o in options])
        llm.set_model(choice)
        if models is None:
            st.error("Ollama n'est pas lancé : démarre start_ollama.ps1 (ou start_chatbot.bat).")
        else:
            st.success("Ollama est lancé", icon="🟢")

    where = menu_filter(category="" if s.f_cat == ALL else s.f_cat, subcategory="" if s.f_sub == ALL else s.f_sub,
                        source="" if s.f_source == ALL else s.f_source, theme="" if s.f_theme == ALL else s.f_theme)
    parts = [v for v in (s.f_source, s.f_cat, s.f_sub) if v != ALL] + ([f"thème {s.f_theme}"] if s.f_theme != ALL else [])
    return where, " › ".join(parts) or "tous les documents"


def md(text: str) -> str:
    """Streamlit draws formulas between $ $ or $$ $$. The models also write them between \\( \\), \\[ \\] or
    `backticks` (shown as grey code): convert those to $ $."""
    text = re.sub(r"\\\[(.+?)\\\]", lambda m: f"$${m.group(1).strip()}$$", text, flags=re.S)
    text = re.sub(r"\\\((.+?)\\\)", lambda m: f"${m.group(1).strip()}$", text)
    return re.sub(r"`([^`\n]*\\[A-Za-z]+[^`\n]*)`", lambda m: f"${m.group(1).strip()}$", text)


@st.cache_data(max_entries=300)
def page_image(book: str, page: int) -> bytes | None:
    return viewer.page_png(book, page)


def show_sources(sources: list[dict], key: str) -> None:
    """One expandable line per source: preview of the PDF page (8d), passage text, button to open the PDF there."""
    if not sources:
        return
    st.caption("Sources")
    for i, h in enumerate(sources, 1):
        extra = f"  ·  distance {h['distance']:.2f}" if "distance" in h else ""
        with st.expander(f"[{i}] {cite(h)}  ·  {h.get('category', '')}{extra}"):
            if not viewer.pdf_exists(h):
                st.caption("PDF non inclus dans cette copie : seul le passage est affiché.")
                st.text(h.get("text", ""))
                continue
            st.button(f"📄 Ouvrir le PDF à la page {h['page_start']}", key=f"{key}-open-{i}",
                      on_click=viewer.open_source, args=(h,))
            left, right = st.columns([2, 3]) if h.get("text") else (st.container(), None)
            img = page_image(h["book"], int(h["page_start"]))
            if img:
                left.image(img, caption=f"Page {h['page_start']} du PDF")
            if right:
                right.text(h["text"])


MODES = {"question": "💬 Question", "explication": "🎓 Explication", "synthese": "🧩 Synthèse",
         "resume": "📄 Résumé d'un document"}
MODE_HELP = {
    "question": "Réponse précise tirée des documents, avec ses sources (~30 s).",
    "explication": "Explication pédagogique adaptée à ton niveau, à partir des documents (~30-60 s).",
    "synthese": "Ce que disent plusieurs documents sur un sujet, regroupé par idées (modèle fort, ~2-3 min).",
    "resume": "Résumé d'un document entier (article TI ou livre) : ~5 min pour un article, plus pour un livre. "
              "Un résumé déjà fait s'affiche tout de suite.",
}
PLACEHOLDERS = {"question": "Pose ta question (français ou anglais)",
                "explication": "Quelle notion veux-tu comprendre ?",
                "synthese": "Sur quel sujet veux-tu une synthèse ?"}


def stream_box():
    """A text area filled as the model writes, + the on_token callback for llm.chat."""
    box, parts = st.empty(), []
    box.markdown("_Recherche dans les documents…_")

    def on_token(piece: str) -> None:
        parts.append(piece)
        box.markdown(md("".join(parts)) + "▌")
    return box, on_token


def add_message(role: str, text: str, sources: list[dict] | None = None) -> None:
    st.session_state.messages.append({"role": role, "text": text, "sources": sources or []})


def ollama_or_stop() -> None:
    if installed_models() is None:
        st.error("Ollama n'est pas lancé : démarre start_ollama.ps1 (ou start_chatbot.bat), puis réessaie.")
        st.stop()


def failed(e: Exception) -> None:
    """A clear message instead of Streamlit's error page; the details go to the terminal of the app."""
    print(f"ERROR in the app: {e!r}", flush=True)
    st.error(f"Le modèle n'a pas pu répondre ({type(e).__name__}). Réessaie, ou choisis un filtre plus précis.\n\n"
             f"Détail : {str(e)[:300]}")
    st.stop()


def run_chat_mode(mode: str, text_in: str, level: str, where: dict | None, where_text: str) -> None:
    """Question, explanation or synthesis: same chat, different function and model (see llm.MODE_MODEL)."""
    shown = {"question": text_in, "explication": f"🎓 **Explication ({level})** : {text_in}",
             "synthese": f"🧩 **Synthèse** : {text_in}"}[mode]
    add_message("user", shown)
    with st.chat_message("user"):
        st.markdown(shown)
    with st.chat_message("assistant"):
        ollama_or_stop()
        box, on_token = stream_box()
        try:
            if mode == "question":
                result = retrieve(text_in, where)
                if result["sources"]:
                    generate("question", SYSTEM_PROMPT, result, on_token=on_token)
                else:
                    result["answer"] = NOT_FOUND[result["lang"]]
            elif mode == "explication":
                result = modes.explain(text_in, level, where, on_token=on_token)
            else:
                result = modes.synthesise(text_in, where, on_token=on_token)
        except Exception as e:
            failed(e)
        box.markdown(md(result["answer"]))
        if "model" in result:
            st.caption(f"{result['model']} · {result['timings']['answer_total']:.0f} s · recherche dans : {where_text}")
        add_message("assistant", result["answer"], result["sources"])
        show_sources(result["sources"], key=f"msg{len(st.session_state.messages) - 1}")


@st.cache_data(max_entries=500)
def summary_parts(path: str) -> int:
    return modes.summary_plan({"path": path})["parts"]


def summary_panel() -> None:
    """Résumé mode: find a document by words of its title (inside the sidebar filters), then summarise it."""
    s = st.session_state
    words = st.text_input("Mots du titre du document", key="sum_words", placeholder="ex. : traitement thermique, poutre, TPM")
    if not words.strip():
        return
    docs = [d for d in modes.find_documents(words, limit=200)
            if (s.f_source == ALL or d["source"] == s.f_source) and (s.f_cat == ALL or d["category"] == s.f_cat)
            and (s.f_sub == ALL or d["subcategory"] == s.f_sub)
            and (s.f_theme == ALL or s.f_theme in d["themes"].split(" | "))][:30]
    if not docs:
        st.info("Aucun document avec ces mots dans le titre (et les filtres choisis à gauche).")
        return
    i = st.selectbox(f"Document ({len(docs)} trouvés)", range(len(docs)), key="sum_doc",
                     format_func=lambda k: f"{docs[k]['title'][:90]}  ({docs[k]['pages']} p.)")
    doc = docs[min(i, len(docs) - 1)]
    done = modes.summary_path(doc).exists()
    parts = summary_parts(doc["path"])
    minutes = (parts * modes.SEC_PER_PART + modes.SEC_FINAL) / 60
    st.caption(f"{doc['category']} › {doc['subcategory']} · {doc['pages']} pages · "
               + ("✅ résumé déjà fait : affichage immédiat" if done else f"⏱️ durée estimée ~{minutes:.0f} min ({parts} parties)"))
    if not st.button("Résumer ce document", type="primary"):
        return
    shown = f"📄 **Résumé** : {doc['title']}"
    add_message("user", shown)
    with st.chat_message("user"):
        st.markdown(shown)
    with st.chat_message("assistant"):
        ollama_or_stop()
        status = st.status("Résumé en cours…", expanded=True) if not done else None
        box, on_token = stream_box()
        try:
            r = modes.summarise_document(doc, on_token=on_token, on_progress=status.write if status else None)
        except Exception as e:
            failed(e)
        if status:
            status.update(label=f"Résumé terminé en {r['seconds'] / 60:.1f} min", state="complete", expanded=False)
        box.markdown(md(r["answer"]))
        source = {"book": doc["path"], "page_start": 1, "page_end": int(doc["pages"] or 1), "printed_start": "",
                  "printed_end": "", "title": doc["title"], "ti_code": doc["ti_code"], "category": doc["category"]}
        add_message("assistant", r["answer"], [source])
    st.rerun()  # redraw: the new summary goes into the conversation, above this panel


where, where_text = sidebar()
st.title("📚 Bibliothèque technique")
st.caption("Réponses tirées des Techniques de l'Ingénieur et des livres techniques, avec leurs sources. "
           f"100 % hors ligne. Recherche dans : **{where_text}**")
mode = st.segmented_control("Mode", list(MODES), format_func=MODES.get, key="mode", default="question",
                            label_visibility="collapsed") or "question"
level = "étudiant"
if mode == "explication":
    level = st.segmented_control("Niveau", list(modes.LEVELS), key="level", default="étudiant") or "étudiant"
st.caption(MODE_HELP[mode] + f"  Modèle : {llm.model_for(mode)}.")

if "messages" not in st.session_state:
    st.session_state.messages = []   # {"role": "user"/"assistant", "text": ..., "sources": [...]}

for n, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        st.markdown(md(m["text"]))
        if m["role"] == "assistant":
            show_sources(m.get("sources", []), key=f"msg{n}")

if mode == "resume":
    summary_panel()
else:
    prompt = st.chat_input(PLACEHOLDERS[mode])
    if prompt:
        run_chat_mode(mode, prompt, level, where, where_text)
