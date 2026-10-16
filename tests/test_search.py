"""Part 5 check: search the vector database with French and English questions.

Shows the top 3 chunks per question with their distance (0 = same meaning; lower is better).
Run (Ollama must be running):  .venv\\Scripts\\python.exe tests\\test_search.py
"""
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from search import cite, search  # noqa: E402

QUESTIONS = [
    # same topic in two languages: should find PDF p. 99-100 (constant torque / constant power)
    "couple constant et puissance constante dans la caractéristique de traction",
    "constant torque and constant power zones of the traction characteristic",
    # specific lookup in a table (PDF p. ~499-500, tightening torques)
    "couple de serrage d'une vis M16",
    "tightening torque for an M16 screw",
    # safety procedure (chapter 2)
    "comment mettre à la terre la motrice avant d'intervenir sur la haute tension",
    # not in the manual at all: distances should be clearly worse
    "recette de la tarte aux pommes",
]

for q in QUESTIONS:
    start = time.time()
    hits = search(q, k=3)
    print(f"\nQ: {q}   ({time.time() - start:.2f} s)")
    for h in hits:
        print(f"  [{h['distance']:.3f}] {cite(h)}")
        print(f"          {h['text'][:110]!r}")
