"""Prompt templates for check_frame and watch_frame (ai/tasks/04, AI-04.1).

Templates are Markdown files next to this module, with {{NAME}} placeholders. They are package
data, so they ship with the package; nothing outside the package is read.
"""

from __future__ import annotations

import re
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=8)
def template(name: str) -> str:
    return (files(__package__) / f"{name}.md").read_text(encoding="utf-8")


_PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")


def render(name: str, **values: str) -> str:
    """Fill {{KEY}} placeholders in one pass.

    The placeholders are read from the template, not from the result, so values may contain any
    text, including "{{" or another placeholder's name, without breaking or being re-filled
    (recipe titles, step text and transcripts come from users). A mismatch between the template's
    placeholders and the given keys is a programming error and raises KeyError.
    """
    text = template(name)
    wanted = set(_PLACEHOLDER.findall(text))
    given = set(values)
    if wanted != given:
        raise KeyError(f"prompt {name!r} placeholders {sorted(wanted)} != given {sorted(given)}")
    return _PLACEHOLDER.sub(lambda m: values[m.group(1)], text)
