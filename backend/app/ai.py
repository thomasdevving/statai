"""The single import point for the ghostchef_ai package (API-CONTRACT §7).

ghostchef_ai is installed separately (`pip install -e ../ai`). If it is not installed the server
still starts so the parts that do not need it work, but anything that needs AI raises
AINotInstalled with a clear message, and /health reports ai_mode "unavailable".
"""

from __future__ import annotations

from types import ModuleType

try:  # pragma: no cover - exercised implicitly by import
    import ghostchef_ai as _ghostchef_ai
except ModuleNotFoundError as exc:  # pragma: no cover
    if exc.name != "ghostchef_ai":
        raise
    _ghostchef_ai = None


class AINotInstalled(RuntimeError):
    pass


def available() -> bool:
    return _ghostchef_ai is not None


def get() -> ModuleType:
    if _ghostchef_ai is None:
        raise AINotInstalled(
            "ghostchef_ai is not installed; run `pip install -e ../ai` (needs AI-01 on main)"
        )
    return _ghostchef_ai


def ai_mode() -> str:
    if _ghostchef_ai is None:
        return "unavailable"
    from ghostchef_ai import config

    return "fake" if config.is_fake() else "gemini"
