from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_MODEL_PATH = PROJECT_ROOT / ".venv" / "models" / "google-flan-t5-small"

_pipeline = None


def get_local_text2text_pipeline():
    """
    Load the local Hugging Face model without any network access.

    The model files are stored inside `.venv/models/...` so the diploma demo can
    run independently after dependencies and model artifacts are prepared once.
    """

    global _pipeline
    if _pipeline is not None:
        return _pipeline

    if not LOCAL_MODEL_PATH.exists():
        return None

    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")

    try:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, pipeline

        tokenizer = AutoTokenizer.from_pretrained(
            str(LOCAL_MODEL_PATH),
            local_files_only=True,
        )
        model = AutoModelForSeq2SeqLM.from_pretrained(
            str(LOCAL_MODEL_PATH),
            local_files_only=True,
        )
        _pipeline = pipeline("text2text-generation", model=model, tokenizer=tokenizer)
        return _pipeline
    except Exception:
        return None


def generate_local_text(prompt: str, max_length: int = 180) -> str | None:
    pipe = get_local_text2text_pipeline()
    if pipe is None:
        return None

    try:
        result = pipe(prompt, max_length=max_length, do_sample=False)
        text = result[0]["generated_text"].strip()
    except Exception:
        return None

    return text or None
