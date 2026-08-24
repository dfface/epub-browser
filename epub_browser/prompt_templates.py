"""Versioned, package-local contracts for AI reading generation."""

import json
from functools import lru_cache
from importlib import resources


@lru_cache(maxsize=1)
def reading_layer_template() -> dict:
    source = (
        resources.files("epub_browser")
        .joinpath("prompt_templates/reading-layer.json")
        .read_text(encoding="utf-8")
    )
    template = json.loads(source)
    if not isinstance(template, dict) or not isinstance(template.get("id"), str):
        raise RuntimeError("Invalid reading layer prompt template")
    if not isinstance(template.get("version"), int) or not isinstance(template.get("system"), str):
        raise RuntimeError("Invalid reading layer prompt template")
    return template


@lru_cache(maxsize=1)
def chapter_reading_layer_template() -> dict:
    source = (
        resources.files("epub_browser")
        .joinpath("prompt_templates/chapter-reading-layer.json")
        .read_text(encoding="utf-8")
    )
    template = json.loads(source)
    if not isinstance(template, dict) or not isinstance(template.get("id"), str):
        raise RuntimeError("Invalid chapter reading layer prompt template")
    if not isinstance(template.get("version"), int) or not isinstance(template.get("system"), str):
        raise RuntimeError("Invalid chapter reading layer prompt template")
    if not isinstance(template.get("research_principles"), str) or not template["research_principles"].strip():
        raise RuntimeError("Invalid chapter reading research principles")
    profiles = template.get("profiles")
    if not isinstance(profiles, dict) or not all(
        isinstance(profiles.get(name), str) and profiles[name].strip()
        for name in ("auto", "technical", "fiction", "general")
    ):
        raise RuntimeError("Invalid chapter reading layer profile prompts")
    return template


def template_for(scope: str, mode: str) -> dict:
    """Return the current immutable template contract for an AI reading task."""
    del mode
    if scope == "chapter":
        return chapter_reading_layer_template()
    return reading_layer_template()


def profile_system_prompt(template: dict, profile: str) -> str:
    """Combine the stable JSON contract with the selected reading lens."""
    profiles = template.get("profiles")
    if not isinstance(profiles, dict):
        return template["system"]
    instruction = profiles.get(profile) or profiles.get("auto")
    if not isinstance(instruction, str) or not instruction.strip():
        raise RuntimeError("Invalid AI reading profile")
    return (
        template["system"]
        + "\n\nReading-comprehension research principles:\n"
        + template["research_principles"].strip()
        + "\n\nProfile guidance:\n"
        + instruction.strip()
    )
