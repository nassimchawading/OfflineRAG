"""Part 11: the chat models and a simple switch between them.

Two models, both in Ollama (see INSTALL_LOG.md):
    "rapide" = qwen3:4b-instruct   ~14 tokens/s on real RAG prompts, mostly on the GPU: questions,
                                    explanations, translation, first pass of long summaries
    "fort"   = qwen3:8b            ~3.5 tokens/s, half on the CPU: syntheses, final step of summaries
Each task ("mode") has a default model in MODE_MODEL. set_model("fort") forces one model for every
task, set_model("auto") goes back to the defaults. To try another Ollama model, change MODELS.
"""
import time

import ollama

MODELS = {"rapide": "qwen3:4b-instruct", "fort": "qwen3:8b"}
THINKING_MODELS = {"qwen3:8b"}  # hybrid models: need think=False, otherwise they write out their reasoning
MODE_MODEL = {
    "question": "rapide",       # normal RAG answer
    "traduction": "rapide",     # English question -> French search query
    "explication": "rapide",    # personalised explanation: the 4B did better than the 8B in the test
                                #   (real analogy, more citations, 2.5x faster; notes\part11_results.md)
    "synthese": "fort",         # synthesis of a subject over several documents
    "resume_partie": "rapide",  # summary of one part of a document (many calls: must be fast)
    "resume": "fort",           # final summary of a document, from the part summaries
}
_forced: str | None = None


def set_model(key: str) -> None:
    """'rapide' or 'fort' = this model for every task; 'auto' = the default model of each task."""
    global _forced
    if key != "auto" and key not in MODELS:
        raise ValueError(f"model must be one of {list(MODELS)} or 'auto'")
    _forced = None if key == "auto" else key


def current_choice() -> str:
    return _forced or "auto"


def model_for(mode: str) -> str:
    return MODELS[_forced or MODE_MODEL[mode]]


def chat(mode: str, messages: list[dict], num_ctx: int = 4096, temperature: float = 0.2, on_token=None) -> dict:
    """Ask the model of this mode. on_token(text) is called for each piece of the answer as it is written
    (print it in the terminal, or show it in the app). Raises ollama.ResponseError if the prompt is too long."""
    model = model_for(mode)
    extra = {"think": False} if model in THINKING_MODELS else {}
    start, parts, final = time.time(), [], None
    for chunk in ollama.chat(model=model, messages=messages, stream=True,
                             options={"temperature": temperature, "num_ctx": num_ctx}, **extra):
        if on_token:
            on_token(chunk.message.content)
        parts.append(chunk.message.content)
        final = chunk
    return {"text": "".join(parts).strip(), "model": model, "num_ctx": num_ctx, "seconds": time.time() - start,
            "load_s": (final.load_duration or 0) / 1e9, "prompt_tokens": final.prompt_eval_count or 0,
            "answer_tokens": final.eval_count or 0,
            "tokens_per_s": final.eval_count / (final.eval_duration / 1e9) if final.eval_duration else 0.0}
