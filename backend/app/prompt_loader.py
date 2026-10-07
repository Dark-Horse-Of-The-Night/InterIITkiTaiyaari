"""Load LLM prompts from backend/app/prompts/*.md. Prompts never live inline in code."""

from functools import lru_cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


@lru_cache
def load_prompt(name: str) -> str:
    """Return the text of prompts/<name>.md."""
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text(encoding="utf-8")
