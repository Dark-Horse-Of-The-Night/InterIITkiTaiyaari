import pytest

from app.prompt_loader import load_prompt


def test_refiner_prompt_contains_key_rules() -> None:
    prompt = load_prompt("refiner")

    assert "{{GLOSSARY}}" in prompt
    for rule in ["names", "numbers", "negation", "commitments", "ONLY the segments you changed"]:
        assert rule in prompt


def test_missing_prompt_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")


def test_documenter_prompt_contains_key_rules() -> None:
    prompt = load_prompt("documenter")

    for rule in ["proposal is not a decision", "unaccepted suggestion is not a task", "Never invent them", "quote"]:
        assert rule in prompt
