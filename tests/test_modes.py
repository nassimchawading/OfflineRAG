"""Part 11 test: model switch, explanations by level, synthesis, document summary (+ saved copy).

Uses the 10 test documents already indexed (tests\\test_menus.py). Writes every answer, its sources and
timings to notes\\part11_results.md to judge the quality. Takes ~10 min (the strong model is slow).

Run (Ollama must be running):  .venv\\Scripts\\python.exe tests\\test_modes.py
"""
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8")

import llm
import modes
from ask import answer
from search import cite

OUT = ROOT / "notes" / "part11_results.md"
lines = ["# Part 11 test results: explanations, synthesis, summaries\n",
         f"Run {time.strftime('%Y-%m-%d %H:%M')}, on the 10 test documents of tests\\test_menus.py.\n"]


def log(title: str, r: dict) -> None:
    sources = "\n".join(f"- [{i}] {cite(h)} (distance {h['distance']:.3f})" for i, h in enumerate(r.get("sources", []), 1))
    stats = (f"{r.get('model', '-')}, {r['timings']['answer_total']:.0f} s (load {r['timings']['model_load']:.0f} s), "
             f"{r['tokens_per_s']:.1f} tokens/s, {r['answer_tokens']} tokens, prompt {r['prompt_tokens']}/{r['num_ctx']}"
             if "model" in r else "no model call")
    lines.extend([f"\n## {title}\n", f"*{stats}*\n", r["answer"] + "\n", "Sources:\n" + sources + "\n"])
    print(f"\n=== {title}\n{stats}\n{r['answer'][:300]}...")


# 1. switch (no Ollama needed)
assert llm.model_for("question") == llm.MODELS["rapide"] and llm.model_for("explication") == llm.MODELS["rapide"]
assert llm.model_for("synthese") == llm.MODELS["fort"] and llm.model_for("resume") == llm.MODELS["fort"]
llm.set_model("fort")
assert llm.model_for("question") == llm.MODELS["fort"]
llm.set_model("auto")
try:
    llm.set_model("enorme")
    raise AssertionError("an unknown model name must be refused")
except ValueError:
    pass
print("1. model switch: OK")

Q = "Qu'est-ce qu'un banc d'essai SPEC et à quoi sert-il ?"
log("2. Normal question (auto = rapide)", answer(Q, stream=False))
log("3a. Explication niveau débutant (auto = rapide)", modes.explain(Q, "débutant"))
log("3b. Explication niveau ingénieur (auto = rapide)", modes.explain(Q, "ingénieur"))
llm.set_model("fort")
log("3c. Explication niveau débutant, modèle forcé fort (comparaison)", modes.explain(Q, "débutant"))
llm.set_model("auto")
log("4. Synthèse : surveillance vibratoire des machines", modes.synthesise("surveillance vibratoire des machines"))

docs = modes.find_documents("performance processeurs")
assert docs, "H2546 not found in the catalogue"
doc = docs[0]
plan = modes.summary_plan(doc)
print(f"\n5. summary of {doc['title']}: {plan}")
r = modes.summarise_document(doc, refresh=True, on_progress=lambda t: print("  ...", t, flush=True))
lines.extend([f"\n## 5. Résumé du document « {doc['title']} » ({doc['pages']} p.)\n",
              f"*{r['parts']} parties, {r['seconds']:.0f} s (estimation {plan['seconds']} s), final {r['model']} "
              f"{r['tokens_per_s']:.1f} tokens/s*\n", r["answer"] + "\n"])
print(r["answer"][:400])
start = time.time()
again = modes.summarise_document(doc)
assert again["cached"] and again["answer"] == r["answer"], "second request must come from data/summaries"
print(f"6. same summary again: from the saved copy in {time.time() - start:.2f} s")
lines.append(f"\n## 6. Même résumé redemandé\n\nLu dans data\\summaries en {time.time() - start:.2f} s.\n")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"\nresults written to {OUT.relative_to(ROOT)}")
