"""Prompt templates for check_frame and watch_frame (ai/tasks/04, AI-04.1).

Templates are Markdown files next to this module, with {{NAME}} placeholders. They are package
data, so they ship with the package; nothing outside the package is read.
"""

from __future__ import annotations

from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=8)
def template(name: str) -> str:
    return (files(__package__) / f"{name}.md").read_text(encoding="utf-8")


def render(name: str, **values: str) -> str:
    """Fill {{KEY}} placeholders. Every placeholder in the template must be given, and no more."""
    text = template(name)
    for key, value in values.items():
        token = "{{" + key + "}}"
        if token not in text:
            raise KeyError(f"prompt {name!r} has no placeholder {token}")
        text = text.replace(token, value)
    if "{{" in text:
        raise KeyError(f"prompt {name!r} has unfilled placeholders")
    return text
