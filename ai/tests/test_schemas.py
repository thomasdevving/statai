import pytest
from pydantic import ValidationError

from ghostchef_ai.schemas import CheckResult, RecipeDraft, StepSpec, WatchFor, clamp_words

WF = dict(id="rice_too_thick", mistake="m", headline="Too much rice",
          fix="Spread thinner, 2cm nori free", spoken="s")


def step(**over):
    base = dict(idx=3, title="Spread rice", key_line="Thin layer, leave 2cm top",
                instruction="i", timestamp_s=74.5, success_criteria=["c"], watch_fors=[WF])
    base.update(over)
    return base


def test_valid_step_parses():
    s = StepSpec.model_validate(step())
    assert s.watch_fors[0].id == "rice_too_thick"
    assert s.watch_for("rice_too_thick") is s.watch_fors[0]
    assert s.watch_for("nope") is None


@pytest.mark.parametrize("field,value", [
    ("title", "one two three four five"),
    ("key_line", "one two three four five six seven eight nine"),
])
def test_step_word_limits(field, value):
    with pytest.raises(ValidationError):
        StepSpec.model_validate(step(**{field: value}))


@pytest.mark.parametrize("field,value", [
    ("headline", "one two three four five"),
    ("fix", "one two three four five six seven eight nine"),
    ("id", "Bad-Id"),
    ("id", "1starts_with_digit"),
])
def test_watch_for_limits(field, value):
    with pytest.raises(ValidationError):
        WatchFor.model_validate({**WF, field: value})


def test_duplicate_watch_for_ids_raise():
    with pytest.raises(ValidationError, match="duplicate"):
        StepSpec.model_validate(step(watch_fors=[WF, WF]))


def test_idx_at_least_one():
    with pytest.raises(ValidationError):
        StepSpec.model_validate(step(idx=0))


def test_recipe_idx_must_be_consecutive():
    with pytest.raises(ValidationError, match="idx"):
        RecipeDraft(title="t", transcript="x", steps=[StepSpec.model_validate(step(idx=2))])


def test_check_result_rejects_unknown_verdict():
    with pytest.raises(ValidationError):
        CheckResult(verdict="maybe", mistake_id=None, headline="h", fix="", spoken="s",
                    confidence=0.5, model="m")


@pytest.mark.parametrize("conf", [-0.1, 1.1])
def test_confidence_range(conf):
    with pytest.raises(ValidationError):
        CheckResult(verdict="pass", mistake_id=None, headline="h", fix="", spoken="s",
                    confidence=conf, model="m")


def test_clamp_words():
    assert clamp_words("Spread it much thinner, please, right now", 4) == "Spread it much thinner"
    assert clamp_words("Too  much   rice", 4) == "Too much rice"
