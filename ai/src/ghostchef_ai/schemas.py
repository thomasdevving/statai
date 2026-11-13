"""Pydantic models of the backend <-> ai interface (docs/API-CONTRACT.md §7).

Field names match the HTTP contract (§2, §3, §5) exactly. Validators enforce the
contract's display limits so a bad fixture or a bad model output fails loudly.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

WATCH_FOR_ID = re.compile(r"^[a-z][a-z0-9_]*$")


def word_count(text: str) -> int:
    return len(text.split())


def clamp_words(text: str, n: int) -> str:
    """Keep at most n whitespace-separated words, dropping trailing punctuation left dangling."""
    words = text.split()
    if len(words) <= n:
        return " ".join(words)
    return " ".join(words[:n]).rstrip(",;:—-– ")


def _limit(value: str, n: int, field: str) -> str:
    if word_count(value) > n:
        raise ValueError(f"{field} must be at most {n} words, got {word_count(value)}: {value!r}")
    return value


class WatchFor(BaseModel):
    id: str
    mistake: str
    headline: str
    fix: str
    spoken: str

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not WATCH_FOR_ID.match(v):
            raise ValueError(f"watch_for id must match {WATCH_FOR_ID.pattern}: {v!r}")
        return v

    @field_validator("headline")
    @classmethod
    def _headline(cls, v: str) -> str:
        return _limit(v, 4, "headline")

    @field_validator("fix")
    @classmethod
    def _fix(cls, v: str) -> str:
        return _limit(v, 8, "fix")


class StepSpec(BaseModel):
    idx: int = Field(ge=1)
    title: str
    key_line: str
    instruction: str
    chef_quote: str | None = None
    timestamp_s: float
    clip_start_s: float | None = None
    clip_end_s: float | None = None
    success_criteria: list[str]
    watch_fors: list[WatchFor]
    timer_s: int | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _limit(v, 4, "title")

    @field_validator("key_line")
    @classmethod
    def _key_line(cls, v: str) -> str:
        return _limit(v, 8, "key_line")

    @model_validator(mode="after")
    def _unique_watch_for_ids(self) -> StepSpec:
        ids = [w.id for w in self.watch_fors]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate watch_for ids in step {self.idx}: {dupes}")
        return self

    def watch_for(self, mistake_id: str | None) -> WatchFor | None:
        return next((w for w in self.watch_fors if w.id == mistake_id), None)


class RecipeDraft(BaseModel):
    title: str
    transcript: str
    steps: list[StepSpec]

    @model_validator(mode="after")
    def _consecutive_idx(self) -> RecipeDraft:
        got = [s.idx for s in self.steps]
        want = list(range(1, len(self.steps) + 1))
        if got != want:
            raise ValueError(f"steps must have idx 1..{len(self.steps)} in order, got {got}")
        return self

    def step(self, idx: int) -> StepSpec:
        for s in self.steps:
            if s.idx == idx:
                return s
        raise KeyError(f"no step {idx} in recipe {self.title!r}")


class CheckResult(BaseModel):
    verdict: Literal["pass", "fix", "unsure"]
    mistake_id: str | None
    headline: str
    fix: str
    spoken: str
    confidence: float = Field(ge=0.0, le=1.0)
    model: str


class WatchResult(BaseModel):
    status: Literal["ok", "warn"]
    mistake_id: str | None
    headline: str
    fix: str
    spoken: str
    confidence: float = Field(ge=0.0, le=1.0)
    model: str


class LiveConfig(BaseModel):
    model: str
    system_instruction: str
    response_modalities: list[str]
    voice: str | None
    tools: list[dict]
    session_resumption: bool


class LiveToken(BaseModel):
    token: str
    expires_at: datetime
    new_session_expires_at: datetime
    locked: bool
