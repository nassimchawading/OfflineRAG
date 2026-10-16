OfflineRAG - chat with technical PDFs, 100% offline
====================================================

A local chatbot (RAG) that answers questions from a library of technical PDFs
(French / English) and cites the source pages. Nothing is sent to the internet:
the models run on your own PC with Ollama.

  PDFs -> extract text -> chunks -> embeddings (bge-m3) -> ChromaDB
  Question -> search ChromaDB -> best passages -> local LLM (Qwen3) -> answer + sources

Tested on: Windows 10, 16 GB RAM, NVIDIA RTX 3050 4 GB (a GPU is optional, CPU works, slower).
The PDFs, the vector database and the models are NOT in this repository (too big).


1. Python + libraries
---------------------
Install Python 3.12 (64-bit), then in PowerShell, from the project folder:

  python -m venv .venv
  .\.venv\Scripts\python.exe -m pip install -r requirements.txt


2. Ollama (portable, nothing installed in Windows)
--------------------------------------------------
- Download "ollama-windows-amd64.zip" from https://github.com/ollama/ollama/releases
- Extract it into the project folder as:  tools\ollama\   (so tools\ollama\ollama.exe exists)
- Start the server (keep this window open, Ctrl+C to stop):

  powershell -NoProfile -ExecutionPolicy Bypass -File .\start_ollama.ps1

  start_ollama.ps1 stores the models in .\models, listens on 127.0.0.1 only and
  turns on settings that help small GPUs (flash attention, q8_0 KV cache).
  It also sets OLLAMA_VULKAN=0 (Vulkan GPU detection hangs on some laptops).


3. Models (in a SECOND PowerShell window, Ollama running; they go into .\models)
--------------------------------------------------------------------------------
  .\tools\ollama\ollama.exe pull qwen3:4b-instruct    # chat model, 2.5 GB (required)
  .\tools\ollama\ollama.exe pull bge-m3               # embedding model FR/EN, 1.2 GB (required)
  .\tools\ollama\ollama.exe pull qwen3:8b             # stronger model, 5.2 GB (optional:
                                                      # summaries / syntheses, slower)

Remove a model:  .\tools\ollama\ollama.exe rm <name>


4. Optional: OCR for scanned PDFs
---------------------------------
Download fra.traineddata from https://github.com/tesseract-ocr/tessdata
into tools\tessdata\  (used by src\ocr.py through PyMuPDF).


5. Use it
---------
- Put your PDFs in data\pdfs\ (any sub-folders), then build the catalogue + index:

  .\.venv\Scripts\python.exe src\add_pdfs.py

- Chat in the browser (http://localhost:8501):

  .\.venv\Scripts\python.exe -m streamlit run src\app.py

- Or in the terminal:

  .\.venv\Scripts\python.exe src\ask.py
