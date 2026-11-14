"""Gemini Live: configuration (pure) and ephemeral-token minting (ai/tasks/05).

build_live_config is pure: the system instruction is prompts/live_system.md plus the recipe.
mint_live_token mints a single-use ephemeral token on API version v1beta and tries to lock the
whole configuration into it, so the phone sends no config of its own (API-CONTRACT §5).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from ghostchef_ai.client import call_with_budget, gemini_client
from ghostchef_ai.config import model_ids
from ghostchef_ai.errors import AIQuotaError, AITimeout, AIUnavailable
from ghostchef_ai.prompts import render
from ghostchef_ai.schemas import LiveConfig, LiveToken, StepSpec

# Ephemeral tokens and Live both need an explicit API version: the SDK default answered HTTP 404
# (AI-02), and the token docs say tokens work "only with the v1beta version". The backend
# returns this as `api_version` in GET /live-token.
LIVE_API_VERSION = "v1beta"

TOKEN_USES = 1
TOKEN_LIFETIME = timedelta(minutes=30)
NEW_SESSION_WINDOW = timedelta(minutes=2)
MINT_TIMEOUT_S = 10.0

# Transcripts longer than this keep their beginning and end (AI-05.1).
MAX_TRANSCRIPT_WORDS = 6000

# The five voice commands of API-CONTRACT §5.2. No parameters. Descriptions list natural
# phrasings so the model triggers on them.
#
# The four commands the app answers itself are NON_BLOCKING, and the phone sends their tool
# response with "scheduling": "SILENT" ("only add the result to the conversation context, do not
# interrupt or trigger generation"). With ordinary blocking functions the model spoke after the
# tool response despite the instruction (AI-05.3, 2026-11-14); with SILENT it stayed quiet 5/5.
# repeat_instruction stays blocking: the model must read the result aloud.
SILENT_FUNCTIONS = ("check_my_work", "next_step", "previous_step", "show_me")

FUNCTION_DECLARATIONS: list[dict] = [
    {
        "name": "check_my_work",
        "description": "Check the cook's work with the camera. Call when the cook asks whether "
        "their work is right, e.g. 'is this okay?', 'is this right?', 'check this', "
        "'does this look good?', 'did I do it right?'.",
        "behavior": "NON_BLOCKING",
    },
    {
        "name": "next_step",
        "description": "Move to the next step. Call when the cook says e.g. 'what's next', "
        "'next step', 'next', 'I'm done', 'done with this one', 'move on'.",
        "behavior": "NON_BLOCKING",
    },
    {
        "name": "previous_step",
        "description": "Go back one step. Call when the cook says e.g. 'go back', "
        "'previous step', 'back one', 'the step before'.",
        "behavior": "NON_BLOCKING",
    },
    {
        "name": "show_me",
        "description": "Play the chef's clip for the current step. Call when the cook says e.g. "
        "'show me how', 'show me', 'how does the chef do it?', 'let me see it'.",
        "behavior": "NON_BLOCKING",
    },
    {
        "name": "repeat_instruction",
        "description": "Get the current step's instruction, then read it aloud to the cook. "
        "Call when the cook says e.g. 'say that again', 'repeat that', 'what do I do now?', "
        "'what was the step?'.",
    },
]


def _transcript_block(transcript: str) -> str:
    words = transcript.split()
    if len(words) <= MAX_TRANSCRIPT_WORDS:
        return transcript.strip()
    n_head, n_tail = MAX_TRANSCRIPT_WORDS * 2 // 3, MAX_TRANSCRIPT_WORDS // 3
    omitted = len(words) - n_head - n_tail
    return (f"{' '.join(words[:n_head])}\n"
            f"[… {omitted} words from the middle of the transcript omitted …]\n"
            f"{' '.join(words[-n_tail:])}")


def _lesson(recipe_title: str, chef_name: str | None, transcript: str,
            steps: list[StepSpec]) -> str:
    lines = [f"Recipe: {recipe_title}"]
    if chef_name:
        lines.append(f"Chef: {chef_name}")
    lines += ["", f"Steps ({len(steps)}):"]
    for s in steps:
        lines.append(f"Step {s.idx}: {s.title} — {s.instruction}")
        for c in s.success_criteria:
            lines.append(f"  Looks right when: {c}")
        if s.timer_s:
            lines.append(f"  Timer: {s.timer_s} seconds")
    lines += ["", "Chef's transcript (what the chef said while cooking):",
              _transcript_block(transcript)]
    return "\n".join(lines)


def build_live_config(
    recipe_title: str, chef_name: str | None, transcript: str, steps: list[StepSpec]
) -> LiveConfig:
    """Pure: no network. The shape is API-CONTRACT §7 `LiveConfig`."""
    return LiveConfig(
        model=model_ids()["live"],
        system_instruction=render(
            "live_system", LESSON=_lesson(recipe_title, chef_name, transcript, steps)
        ),
        response_modalities=["AUDIO"],
        voice=None,  # the model's default voice
        tools=[{"function_declarations": [dict(d) for d in FUNCTION_DECLARATIONS]}],
        session_resumption=True,
    )


# --------------------------------------------------------------------------- token


def locked_setup(cfg: LiveConfig) -> dict[str, Any]:
    """The Live setup bound into a fully locked token (SDK snake_case form).

    Beyond the contract's LiveConfig this also locks transcription in both directions (the phone
    can show captions and log what was heard) and sliding-window context compression (without
    it, audio-only sessions end after 15 minutes).

    Session resumption is deliberately NOT in the lock: a locked `sessionResumption: {}`
    replaces the handle the phone sends when it reconnects, so the "resumed" session silently
    starts fresh (observed 2026-11-14). The phone sends `sessionResumption` itself; the token
    request uses `lock_additional_fields=[]` so only the fields given here are locked.
    """
    config: dict[str, Any] = {
        "response_modalities": list(cfg.response_modalities),
        "system_instruction": cfg.system_instruction,
        "tools": cfg.tools,
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "context_window_compression": {"sliding_window": {}},
    }
    if cfg.voice:
        config["speech_config"] = {
            "voice_config": {"prebuilt_voice_config": {"voice_name": cfg.voice}}}
    return {"model": cfg.model, "config": config}


def partial_setup(cfg: LiveConfig) -> dict[str, Any]:
    """Fallback lock: model and output modality only; the phone sends the rest in its setup."""
    return {"model": cfg.model, "config": {"response_modalities": list(cfg.response_modalities)}}


def token_request(constraints: dict[str, Any], now: datetime) -> dict:
    return {
        "uses": TOKEN_USES,
        "expire_time": now + TOKEN_LIFETIME,
        "new_session_expire_time": now + NEW_SESSION_WINDOW,
        "live_connect_constraints": constraints,
        # An empty list locks exactly the fields given in the constraints (the SDK sends them as
        # the field mask) and leaves the others, e.g. sessionResumption, to the client. Leaving
        # it out would lock the whole setup, including an empty sessionResumption.
        "lock_additional_fields": [],
    }


def _as_dt(value: Any, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass
    return fallback


async def _create(constraints: dict[str, Any], now: datetime):
    client = gemini_client(LIVE_API_VERSION)
    return await call_with_budget(
        client.aio.auth_tokens.create(config=token_request(constraints, now)), MINT_TIMEOUT_S)


async def mint_live_token(live_config: LiveConfig) -> LiveToken:
    """Mint a single-use token: fully locked if the API accepts it, else partially locked.

    Raises AIError subclasses only. Quota and timeout errors are not retried with a weaker lock.
    """
    now = datetime.now(tz=UTC)
    locked = True
    try:
        tok = await _create(locked_setup(live_config), now)
    except (AIQuotaError, AITimeout):
        raise
    except AIUnavailable:
        # The full lock was rejected (e.g. a field cannot be constrained): lock what can be.
        locked = False
        tok = await _create(partial_setup(live_config), now)
    name = getattr(tok, "name", None) or ""
    if not name.startswith("auth_tokens/"):
        raise AIUnavailable(f"unexpected ephemeral token name prefix {name.split('/')[0]!r}")
    return LiveToken(
        token=name,
        expires_at=_as_dt(getattr(tok, "expire_time", None), now + TOKEN_LIFETIME),
        new_session_expires_at=_as_dt(getattr(tok, "new_session_expire_time", None),
                                      now + NEW_SESSION_WINDOW),
        locked=locked,
    )
