"""Gemini Live configuration (pure) and token minting (real path arrives in AI-05)."""

from __future__ import annotations

from ghostchef_ai.config import model_ids
from ghostchef_ai.errors import AIUnavailable
from ghostchef_ai.schemas import LiveConfig, LiveToken, StepSpec

# The five voice commands of docs/API-CONTRACT.md §5.2. No parameters.
FUNCTION_DECLARATIONS: list[dict] = [
    {
        "name": "check_my_work",
        "description": "The cook asks whether their work looks right, e.g. 'is this okay?', "
        "'check this', 'did I do it right?'.",
    },
    {
        "name": "next_step",
        "description": "The cook wants to move on, e.g. 'what's next', 'next step', 'done'.",
    },
    {
        "name": "previous_step",
        "description": "The cook wants to go back, e.g. 'go back', 'previous step'.",
    },
    {
        "name": "show_me",
        "description": "The cook wants to see the chef do this step, e.g. 'show me how'.",
    },
    {
        "name": "repeat_instruction",
        "description": "The cook wants the current step read again, e.g. 'say that again'.",
    },
]

_FIXED = """You are a calm cooking assistant speaking for this chef's lesson, through smart \
glasses, to someone whose hands are busy. Answer in one or two short sentences, never a list.
Answer from the lesson below. If the chef said it, say so. If the lesson does not cover the \
question, say "The chef doesn't cover that in this lesson". Never invent what the chef said.
You cannot see the camera. Never say whether the food looks right; call check_my_work instead.
When the cook asks to check, go to the next or previous step, see the chef do it, or hear the \
step again, call the matching function and say nothing until the tool response.
Messages starting with [CONTEXT] are state updates from the app. Never reply to them."""


def build_live_config(
    recipe_title: str, chef_name: str | None, transcript: str, steps: list[StepSpec]
) -> LiveConfig:
    """First version (AI-01). AI-05 refines the instruction text; the shape stays."""
    lines = [_FIXED, "", f"RECIPE: {recipe_title}"]
    if chef_name:
        lines.append(f"CHEF: {chef_name}")
    lines.append("STEPS:")
    for s in steps:
        lines.append(f"Step {s.idx}: {s.title} — {s.instruction}")
        for c in s.success_criteria:
            lines.append(f"  - looks right when: {c}")
    lines += ["", "CHEF TRANSCRIPT:", transcript]
    return LiveConfig(
        model=model_ids()["live"],
        system_instruction="\n".join(lines),
        response_modalities=["AUDIO"],
        voice=None,
        tools=[{"function_declarations": [dict(d) for d in FUNCTION_DECLARATIONS]}],
        session_resumption=True,
    )


async def mint_live_token(live_config: LiveConfig) -> LiveToken:
    raise AIUnavailable("mint_live_token is not implemented yet; set GHOSTCHEF_AI_FAKE=1")
