"""Request / response models, field for field from API-CONTRACT §2–§5."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

WATCH_FOR_ID = re.compile(r"^[a-z][a-z0-9_]*$")
FiniteFloat = Annotated[float, Field(allow_inf_nan=False)]


def _max_words(value: str, n: int, name: str) -> str:
    if len(value.split()) > n:
        raise ValueError(f"{name} must be at most {n} words")
    return value


def _non_blank(value: str, name: str) -> str:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


# --------------------------------------------------------------------------- steps


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
            raise ValueError("watch_fors[].id must be snake_case")
        return v

    @field_validator("headline")
    @classmethod
    def _headline(cls, v: str) -> str:
        return _max_words(v, 4, "headline")

    @field_validator("fix")
    @classmethod
    def _fix(cls, v: str) -> str:
        return _max_words(v, 8, "fix")


class StepOut(BaseModel):
    id: str
    recipe_id: str
    idx: int
    title: str
    key_line: str
    instruction: str
    chef_quote: str | None
    timestamp_s: float
    clip_start_s: float | None
    clip_end_s: float | None
    success_criteria: list[str]
    watch_fors: list[dict[str, Any]]
    ref_image_url: str | None
    clip_url: str | None
    timer_s: int | None


class StepPatch(BaseModel):
    """PATCH /steps/{id}: any of these. Explicit null only where the field is nullable."""

    model_config = ConfigDict(extra="ignore")

    title: str | None = None
    key_line: str | None = None
    instruction: str | None = None
    success_criteria: list[str] | None = Field(default=None, max_length=20)
    watch_fors: list[WatchFor] | None = Field(default=None, max_length=20)
    timer_s: int | None = Field(default=None, ge=0, le=24 * 3600)
    timestamp_s: float | None = Field(default=None, ge=0, allow_inf_nan=False)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str | None) -> str | None:
        return None if v is None else _max_words(_non_blank(v, "title"), 4, "title")

    @field_validator("key_line")
    @classmethod
    def _key_line(cls, v: str | None) -> str | None:
        return None if v is None else _max_words(_non_blank(v, "key_line"), 8, "key_line")

    @field_validator("instruction")
    @classmethod
    def _instruction(cls, v: str | None) -> str | None:
        return None if v is None else _non_blank(v, "instruction")

    @field_validator("watch_fors")
    @classmethod
    def _unique_ids(cls, v: list[WatchFor] | None) -> list[WatchFor] | None:
        if v is not None and len({w.id for w in v}) != len(v):
            raise ValueError("watch_fors ids must be unique within a step")
        return v

    @model_validator(mode="after")
    def _no_null_for_required(self) -> StepPatch:
        required = ("title", "key_line", "instruction", "success_criteria", "watch_fors")
        for name in required + ("timestamp_s",):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


# --------------------------------------------------------------------------- recipes


class RecipeListItem(BaseModel):
    id: str
    title: str
    chef_name: str | None
    status: str
    step_count: int
    created_at: datetime


class RecipeList(BaseModel):
    recipes: list[RecipeListItem]


class RecipeDetail(BaseModel):
    id: str
    title: str
    chef_name: str | None
    status: str
    error: str | None
    video_url: str | None
    step_marks_s: list[float]
    transcript: str | None
    created_at: datetime
    steps: list[StepOut]


class RecipeCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=80)
    chef_name: str | None = Field(default=None, max_length=120)
    step_marks_s: list[FiniteFloat] = Field(default_factory=list, max_length=500)
    consent: bool

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        return _non_blank(v, "title")

    @field_validator("step_marks_s")
    @classmethod
    def _marks(cls, v: list[float]) -> list[float]:
        if any(m < 0 for m in v):
            raise ValueError("step_marks_s must be non-negative")
        if any(b <= a for a, b in zip(v, v[1:], strict=False)):
            raise ValueError("step_marks_s must be ascending")
        return v

    @field_validator("consent")
    @classmethod
    def _consent(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("consent must be true")
        return v


class RecipeCreated(BaseModel):
    recipe_id: str
    status: str
    upload_url: str
    upload_token: str
    bucket: str
    object_path: str
    resumable_endpoint: str | None
    upload_expires_at: datetime


class ProcessStarted(BaseModel):
    recipe_id: str
    status: str


class RecipePatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, min_length=1, max_length=80)
    chef_name: str | None = Field(default=None, max_length=120)

    @field_validator("title")
    @classmethod
    def _title(cls, v: str | None) -> str | None:
        return None if v is None else _non_blank(v, "title")

    @model_validator(mode="after")
    def _title_not_null(self) -> RecipePatch:
        if "title" in self.model_fields_set and self.title is None:
            raise ValueError("title cannot be null")
        return self


# --------------------------------------------------------------------------- check / watch


class CheckOut(BaseModel):
    request_id: str
    step_id: str
    verdict: Literal["pass", "fix", "unsure"]
    mistake_id: str | None
    headline: str
    fix: str
    spoken: str
    confidence: float
    latency_ms: int
    model: str


class WatchOut(BaseModel):
    request_id: str
    step_id: str
    status: Literal["ok", "warn"]
    mistake_id: str | None
    headline: str
    fix: str
    spoken: str
    confidence: float
    latency_ms: int
    model: str


# --------------------------------------------------------------------------- sessions

CLIENT_EVENT_KINDS = (
    "step_change",
    "question",
    "warning_shown",
    "warning_dismissed",
    "show_me",
    "client_error",
    "session_end",
)
SERVER_EVENT_KINDS = ("check_pass", "check_fix", "check_unsure", "watch_warn")


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    recipe_id: str
    client: Literal["ios", "web-sim"]
    device_label: str | None = Field(default=None, max_length=200)


class SessionCreated(BaseModel):
    session_id: str
    started_at: datetime


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    step_id: str | None = None
    request_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v in SERVER_EVENT_KINDS:
            raise ValueError(f"{v} is recorded by the server; clients must not post it")
        if v not in CLIENT_EVENT_KINDS:
            raise ValueError(f"unknown event kind {v!r}")
        return v


class EventCreated(BaseModel):
    event_id: str


class EventOut(BaseModel):
    id: str
    kind: str
    step_id: str | None
    request_id: str | None
    payload: dict[str, Any]
    created_at: datetime


class SessionListItem(BaseModel):
    id: str
    recipe_id: str
    recipe_title: str | None
    client: str
    device_label: str | None
    started_at: datetime
    finished_at: datetime | None


class SessionList(BaseModel):
    sessions: list[SessionListItem]


class SessionSummary(BaseModel):
    steps_total: int
    steps_passed_first_try: int
    fixes_caught: int
    warnings: int
    questions: int


class SessionDetail(BaseModel):
    id: str
    recipe_id: str
    client: str
    device_label: str | None
    started_at: datetime
    finished_at: datetime | None
    events: list[EventOut]
    summary: SessionSummary


class MonitorSession(BaseModel):
    id: str
    client: str
    device_label: str | None
    started_at: datetime
    finished_at: datetime | None


class LastResult(BaseModel):
    source: Literal["check", "watch"]
    at: datetime
    body: dict[str, Any]


class Latency(BaseModel):
    check_p50_ms: int | None
    check_max_ms: int | None
    watch_p50_ms: int | None
    watch_max_ms: int | None
    n_check: int
    n_watch: int


class Monitor(BaseModel):
    session: MonitorSession
    recipe_title: str | None
    current_step: StepOut | None
    last_frame_url: str | None
    last_frame_at: datetime | None
    last_result: LastResult | None
    events: list[EventOut]
    latency: Latency


# --------------------------------------------------------------------------- live


class LiveConfigOut(BaseModel):
    system_instruction: str
    response_modalities: list[str]
    voice: str | None
    tools: list[dict[str, Any]]
    session_resumption: bool


class LiveTokenOut(BaseModel):
    token: str
    expires_at: datetime
    new_session_expires_at: datetime
    model: str
    api_version: str
    locked: bool
    config: LiveConfigOut
