import pytest

from app.prompt_loader import load_prompt


def test_refiner_prompt_contains_key_rules() -> None:
    prompt = load_prompt("refiner")

    assert "{{GLOSSARY}}" in prompt
    for rule in ["names", "numbers", "negation", "commitments", "same \"id\""]:
        assert rule in prompt


def test_missing_prompt_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("does_not_exist")
