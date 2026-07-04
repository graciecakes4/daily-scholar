"""
Display preferences: theme + font size (Phase 5 / fd3, foundation slice).

Mirrors backend/services/notifications.py's shape: a small registry (themes,
font sizes) plus per-user settings helpers that read/merge/write the
`UserSettings.display_settings` JSON blob. Adding a new theme or font size
later is a registry entry only — no migration, no UI hardcoding beyond the
picker rendering one entry per registry item.

fd3 scoped in FUTURE_FEATURES.md a much longer theme list (pastel, muted,
high-contrast, pride, colorful accents, black-and-white, random) — this
foundation slice ships the plumbing plus three real themes (editorial,
dark, observatory) and four font sizes. The registry is exactly where the
rest land next: append a THEMES entry, no other code changes needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from ..database import (
    DEFAULT_USER_ID,
    UserSettings,
    get_or_create_user_settings,
    get_session,
)


@dataclass(frozen=True)
class ThemeOption:
    key: str            # stable id; used in settings JSON + data-theme attr
    label: str           # human-facing label for the settings UI
    description: str     # one-line help text
    dark: bool            # drives the browser theme-color / status bar hint


@dataclass(frozen=True)
class FontSizeOption:
    key: str
    label: str
    root_px: int         # <html> base font-size in px for this option


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

THEMES: dict[str, ThemeOption] = {
    "editorial": ThemeOption(
        key="editorial",
        label="Editorial (default)",
        description="Warm cream paper, ink text, gold accents — the original Daily Scholar look.",
        dark=False,
    ),
    "dark": ThemeOption(
        key="dark",
        label="Dark",
        description="Same editorial layout and type, recolored for low light.",
        dark=True,
    ),
    "observatory": ThemeOption(
        key="observatory",
        label="Observatory",
        description="Near-black instrument panel with amber glow and italic serif numerals — a deliberate departure from editorial cream.",
        dark=True,
    ),
}

FONT_SIZES: dict[str, FontSizeOption] = {
    "small": FontSizeOption(key="small", label="Small", root_px=15),
    "medium": FontSizeOption(key="medium", label="Medium (default)", root_px=17),
    "large": FontSizeOption(key="large", label="Large", root_px=19),
    "xlarge": FontSizeOption(key="xlarge", label="Extra large", root_px=21),
}

DEFAULT_DISPLAY_SETTINGS: dict[str, Any] = {
    "theme": "editorial",
    "font_size": "medium",
}


def list_themes() -> list[dict[str, Any]]:
    return [
        {"key": t.key, "label": t.label, "description": t.description, "dark": t.dark}
        for t in THEMES.values()
    ]


def list_font_sizes() -> list[dict[str, Any]]:
    return [
        {"key": f.key, "label": f.label, "root_px": f.root_px}
        for f in FONT_SIZES.values()
    ]


# ---------------------------------------------------------------------------
# Per-user settings
# ---------------------------------------------------------------------------


def ensure_settings_shape(raw: Optional[dict[str, Any]]) -> dict[str, Any]:
    """
    Normalize a stored display_settings blob. Tolerates None / partial /
    stale-registry blobs (e.g. a theme that got removed) by falling back
    to the default for that field. Pure — callers persist if they care.
    """
    raw = dict(raw or {})

    theme = str(raw.get("theme") or DEFAULT_DISPLAY_SETTINGS["theme"])
    if theme not in THEMES:
        theme = DEFAULT_DISPLAY_SETTINGS["theme"]

    font_size = str(raw.get("font_size") or DEFAULT_DISPLAY_SETTINGS["font_size"])
    if font_size not in FONT_SIZES:
        font_size = DEFAULT_DISPLAY_SETTINGS["font_size"]

    return {"theme": theme, "font_size": font_size}


def get_display_settings(user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    """Read + normalize the display_settings blob for `user_id`."""
    settings = get_or_create_user_settings(user_id)
    return ensure_settings_shape(settings.display_settings)


def update_display_settings(user_id: str, new_settings: dict[str, Any]) -> dict[str, Any]:
    """Replace the user's display settings (normalized) and persist."""
    normalized = ensure_settings_shape(new_settings)
    session = get_session()
    try:
        settings = (
            session.query(UserSettings)
            .filter(UserSettings.user_id == user_id)
            .first()
        )
        if settings is None:
            settings = UserSettings(user_id=user_id, scope_mode="all", scope_topic_ids=[])
            session.add(settings)
            session.flush()
        settings.display_settings = normalized
        settings.updated_at = datetime.utcnow()
        session.commit()
    finally:
        session.close()
    return normalized
