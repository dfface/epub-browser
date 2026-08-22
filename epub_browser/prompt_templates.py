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


def template_for(scope: str, mode: str) -> dict:
    """Return the current immutable template contract for an AI reading task."""
    # The first shared contract covers chapter layers and book-level summaries.
    # Future profile-specific templates can be selected here without changing the
    # result persistence or cache-key contract.
    del scope, mode
    return reading_layer_template()
