"""Part 12: build the share kit = a copy of the project that runs on another Windows PC, offline.

Writes kit/OfflineRAG/ (and kit/OfflineRAG_kit.zip with --zip). The project itself is not modified.
What changes compared to the project folder:
- no .venv (it only works from this exact folder): the libraries of .venv are copied into the kit's
  portable Python (tools/python312), which start_chatbot.bat uses when there is no .venv
- only the Ollama models the app uses (bge-m3, qwen3:4b-instruct, and qwen3:8b unless --no-8b)
- no data/_retires, installers, logs, tests, notes, git or project .md files; a LISEZ-MOI.txt is added

Long paths: some TI PDFs have paths of ~220 characters inside the project, so inside kit/OfflineRAG
they pass the 260-character Windows limit. Files are copied and zipped with the "\\\\?\\" long-path form,
and LISEZ-MOI asks to unzip directly to C:\\ (C:\\OfflineRAG\\ + 220 characters stays under 260).

Re-running only copies what changed (same size + date = skipped), so a rebuild after new PDFs is fast.

Run:  .venv\\Scripts\\python.exe src\\prepare_kit.py [--no-pdfs] [--no-8b] [--zip]
"""
from pathlib import Path
import argparse
import json
import shutil
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parent.parent
KIT_DIR = Path("\\\\?\\" + str(ROOT / "kit"))  # long-path form: no 260-character limit
KIT = KIT_DIR / "OfflineRAG"
ZIP = KIT_DIR / "OfflineRAG_kit.zip"

FILES = ["start_chatbot.bat", "start_ollama.ps1", "README.txt", "requirements.txt",
         "data/catalog.csv", "data/catalog_overrides.csv", "data/catalog_cache.json"]
DIRS = ["src", ".streamlit", "tools/ollama", "tools/tessdata", "tools/python312",
        "db", "data/extracted", "data/summaries"]
SKIP_NAMES = {"__pycache__"}
SKIP_SUFFIXES = {".pyc", ".partial"}
MODELS = ["bge-m3/latest", "qwen3/4b-instruct", "qwen3/8b"]
MANIFESTS = Path("models/manifests/registry.ollama.ai/library")
STORED = {".pdf", ".zip", ".dll", ".exe"}  # already compressed (or not worth it): stored as is in the zip

LISEZ_MOI = """\
OfflineRAG - chatbot sur une bibliotheque technique, 100 % hors ligne
=====================================================================

Installation (une seule fois)
  Extraire OfflineRAG_kit.zip DIRECTEMENT dans C:\\  (clic droit -> "Extraire tout..." -> taper C:\\)
  pour obtenir C:\\OfflineRAG\\. Important : certains noms de PDF sont tres longs ; dans un dossier
  plus profond (Telechargements, Bureau...) Windows ne peut pas les extraire (limite de 260 caracteres).

Demarrer : double-cliquer sur C:\\OfflineRAG\\start_chatbot.bat
  - une fenetre "Ollama - OfflineRAG" (reduite) demarre les modeles d'IA,
  - puis l'application s'ouvre dans le navigateur : http://localhost:8501
  - le premier demarrage et la premiere question prennent 30 s a 1 min (chargement des modeles).
Arreter : fermer la fenetre "OfflineRAG - chatbot", puis la fenetre "Ollama - OfflineRAG".

Utilisation : choisir ou chercher dans la barre de gauche (source, categorie, theme), le mode
(Question, Explication, Synthese, Resume d'un document), puis poser la question en francais ou
en anglais. Chaque reponse cite ses sources ; "Ouvrir le PDF" ouvre la page d'origine.

Configuration requise
  - Windows 10/11 64 bits, aucun droit administrateur, aucune connexion Internet
  - 16 Go de RAM recommandes (8 Go : choisir le modele "rapide" dans la barre de gauche)
  - carte NVIDIA conseillee mais pas obligatoire (sans GPU : reponses plus lentes)
  - environ 40 Go libres pendant l'extraction (zip + dossier), 19 Go ensuite (le zip peut etre supprime)

Rien n'est installe dans Windows : tout est dans ce dossier (Python et Ollama portables).
Seule trace : Ollama cree un petit dossier %USERPROFILE%\\.ollama (cle d'identification).
Pour tout supprimer : supprimer C:\\OfflineRAG, puis %USERPROFILE%\\.ollama.

Si Windows affiche "Windows a protege votre ordinateur" : "Informations complementaires" ->
"Executer quand meme" (le fichier .bat vient d'un autre ordinateur).
Si l'application ne demarre pas : regarder les messages dans les deux fenetres.
"""


def copy_file(src: Path, dst: Path) -> int:
    """Copy one file unless the kit already has it (same size and date). Returns bytes copied."""
    st = src.stat()
    if dst.exists():
        d = dst.stat()
        if d.st_size == st.st_size and int(d.st_mtime) == int(st.st_mtime):
            return 0
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return st.st_size


def copy_tree(src: Path, dst: Path) -> int:
    total = 0
    for p in src.rglob("*"):
        if p.is_dir() or SKIP_NAMES & set(p.relative_to(src).parts) or p.suffix in SKIP_SUFFIXES:
            continue
        total += copy_file(p, dst / p.relative_to(src))
    return total


def model_files(names: list[str]) -> list[Path]:
    """Manifest + blob files (relative to ROOT) of the given Ollama models."""
    files = []
    for name in names:
        manifest = MANIFESTS / name
        files.append(manifest)
        data = json.loads((ROOT / manifest).read_text(encoding="utf-8"))
        for layer in [data["config"]] + data["layers"]:
            files.append(Path("models/blobs") / layer["digest"].replace(":", "-"))
    return files


def write_zip():
    """kit/OfflineRAG -> kit/OfflineRAG_kit.zip (zip64: the 8B model is a single 4.9 GB file)."""
    ZIP.unlink(missing_ok=True)
    files = sorted(p for p in KIT.rglob("*") if p.is_file() and p.suffix not in SKIP_SUFFIXES
                   and not SKIP_NAMES & set(p.relative_to(KIT).parts))  # caches made by a test run
    with zipfile.ZipFile(ZIP, "w", allowZip64=True) as z:
        for i, p in enumerate(files, 1):
            rel = p.relative_to(KIT_DIR)
            stored = p.suffix.lower() in STORED or rel.parts[1] == "models"  # model blobs: no gain
            z.write(p, rel.as_posix(), compress_type=zipfile.ZIP_STORED if stored else zipfile.ZIP_DEFLATED,
                    compresslevel=None if stored else 1)
            if i % 1000 == 0:
                print(f"    {i}/{len(files)} files", flush=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Build the share kit in kit/OfflineRAG.")
    ap.add_argument("--no-pdfs", action="store_true", help="leave out data/pdfs (-4.3 GB, no page images)")
    ap.add_argument("--no-8b", action="store_true", help="leave out qwen3:8b (-5.2 GB)")
    ap.add_argument("--zip", action="store_true", help="also write kit/OfflineRAG_kit.zip")
    args = ap.parse_args()

    t0 = time.time()
    dirs = DIRS + ([] if args.no_pdfs else ["data/pdfs"])
    models = [m for m in MODELS if not (args.no_8b and m == "qwen3/8b")]
    copied = 0
    for d in dirs:
        print(f"  {d} ...", flush=True)
        copied += copy_tree(ROOT / d, KIT / d)
    for f in FILES:
        copied += copy_file(ROOT / f, KIT / f)
    print("  models: " + ", ".join(models), flush=True)
    for f in model_files(models):
        copied += copy_file(ROOT / f, KIT / f)
    # The libraries of .venv go into the kit's portable Python (.venv itself cannot be moved).
    print("  libraries (.venv -> tools/python312) ...", flush=True)
    copied += copy_tree(ROOT / ".venv/Lib/site-packages", KIT / "tools/python312/Lib/site-packages")
    (KIT / "LISEZ-MOI.txt").write_text(LISEZ_MOI, encoding="utf-8-sig")
    (KIT_DIR / "LISEZ-MOI.txt").write_text(LISEZ_MOI, encoding="utf-8-sig")  # to share next to the zip

    # Parts the user left out of an earlier build must not stay in the kit.
    if args.no_pdfs and (KIT / "data/pdfs").exists():
        shutil.rmtree(KIT / "data/pdfs")
    keep = {KIT / f for f in model_files(models)}
    for p in (KIT / "models").rglob("*"):
        if p.is_file() and p not in keep:
            p.unlink()

    size = sum(p.stat().st_size for p in KIT.rglob("*") if p.is_file())
    print(f"Kit: {KIT}  ({size / 1e9:.1f} GB, {copied / 1e9:.1f} GB copied, {time.time() - t0:.0f} s)")

    if args.zip:
        print(f"Zip: {ZIP} ...", flush=True)
        t1 = time.time()
        write_zip()
        print(f"Zip: {ZIP.stat().st_size / 1e9:.1f} GB ({time.time() - t1:.0f} s)")


if __name__ == "__main__":
    main()
