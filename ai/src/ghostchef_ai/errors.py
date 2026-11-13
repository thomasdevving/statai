"""Errors raised by ghostchef_ai. Functions in this package raise only these.

HTTP mapping (done by backend/, see docs/API-CONTRACT.md §7):
AITimeout -> 504 model_timeout, AIQuotaError -> 429 quota_exhausted,
AIUnavailable and AIInvalidOutput -> 503 model_unavailable.
"""


class AIError(Exception):
    """Base class for every error this package raises."""


class AITimeout(AIError):
    """The model did not answer within the time budget."""


class AIQuotaError(AIError):
    """Rate limit or quota exhausted."""


class AIUnavailable(AIError):
    """The model call failed for another reason, or the feature is not implemented yet."""


class AIInvalidOutput(AIError):
    """The model answered, but its output did not match the expected schema."""
