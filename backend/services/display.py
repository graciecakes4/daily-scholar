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

Three more themes landed after the foundation: soft_morning and noir
(picked as the two directions that will later grow a multi-hue accent
picker — red/blue/green/purple/orange per fd3's backlog) and brutalist
(a standalone theme, single accent only, no multi-hue variant planned).

Both multi-hue rollouts are in: THEME_ACCENTS registers five options
each for soft_morning (orange/rose/sage/sky/lavender) and noir (cobalt/
crimson/emerald/violet/amber) — same red/blue/green/purple/orange list
from fd3's backlog, named to fit each theme's own palette. Noir's are
fully saturated rather than pastel since a washed-out tint would
disappear against its near-black surfaces.

fd2's "add new fonts" landed as a theme-independent reading_font
setting: READING_FONTS registers "theme" (the no-op default — every
theme's own body font, untouched), "merriweather", and "source_sans".
Scoped to long-form generated content only (globals.css's
.prose-scholar rules), not the app's own theme typography, so it can't
clash with the bespoke fonts each theme below already carries.

fd3's full theme list is now shipped: muted (quiet stone/greige,
single clay accent), high_contrast (pure black/white verified against
WCAG, its own 4-option accent picker — cyan/orange/magenta/violet),
pride (clean neutral base, the progressive flag's palette carried as a
thin ribbon rather than a flood — see its `.app-shell::before` rule in
globals.css), and random — a meta-theme with no CSS block of its own.
`resolve_random()` deterministically hashes user_id + the theme/accent
purpose + the current ISO week (Monday-anchored, UTC) into a pick from
every other registered theme (and that theme's accent pool, if any).
No cron or stored rotation state needed — the week number itself is
the clock, so the reset happens for free at the Sunday/Monday
boundary. `get_display_settings`/`update_display_settings` always
return `resolved_theme`/`resolved_accent` alongside the raw stored
`theme`/`accent`, so the frontend never has to special-case "random"
when deciding what to paint.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from ..database import (
    DEFAULT_USER_ID,
    UserSettings,
    get_or_create_user_settings,
    get_session,
)

RANDOM_THEME_KEY = "random"


@dataclass(frozen=True)
class ThemeOption:
    key: str            # stable id; used in settings JSON + data-theme attr
    label: str           # human-facing label for the settings UI
    description: str     # one-line help text
    dark: bool            # drives the browser theme-color / status bar hint
    is_random: bool = False  # True only for the "random" meta-theme — has
                               # no [data-theme="..."] CSS block of its own;
                               # resolve_random() picks a real theme instead


@dataclass(frozen=True)
class FontSizeOption:
    key: str
    label: str
    root_px: int         # <html> base font-size in px for this option


@dataclass(frozen=True)
class ReadingFontOption:
    key: str    # stable id; used in settings JSON + the data-reading-font attr
    label: str
    description: str


@dataclass(frozen=True)
class AccentOption:
    key: str    # stable id; used in settings JSON + the data-accent attr
    label: str   # human-facing label for the accent swatch
    hex: str      # swatch fill color for the picker UI — the matching
                   # --gold/--gold-dark CSS variables live in globals.css's
                   # [data-theme="..."][data-accent="..."] blocks and must
                   # be kept in sync with this by hand (no single source of
                   # truth yet; small enough registry that this is fine).


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
    "soft_morning": ThemeOption(
        key="soft_morning",
        label="Soft Morning",
        description="Blush pastel warmth, rounded shapes, and a soft coral accent.",
        dark=False,
    ),
    "noir": ThemeOption(
        key="noir",
        label="Noir",
        description="Cold monochrome with a halftone grain and one electric-blue accent cutting through.",
        dark=True,
    ),
    "brutalist": ThemeOption(
        key="brutalist",
        label="Brutalist",
        description="Stark black-and-white, thick hard-edge borders, offset shadows, and a punchy red accent.",
        dark=False,
    ),
    "muted": ThemeOption(
        key="muted",
        label="Muted",
        description="Desaturated stone and greige, hairline rules, a dusty clay accent — an old-library hush.",
        dark=False,
    ),
    "high_contrast": ThemeOption(
        key="high_contrast",
        label="High Contrast",
        description="Pure black and white verified against WCAG, thick borders, and a 4-color accent picker.",
        dark=True,
    ),
    "pride": ThemeOption(
        key="pride",
        label="Pride",
        description="Clean neutral base with the progressive flag's palette carried as a thin ribbon, not a flood.",
        dark=False,
    ),
    "random": ThemeOption(
        key="random",
        label="Random",
        description="A new theme (and accent, if it has one) every week — resets Mondays at midnight UTC, different for every user.",
        dark=False,
        is_random=True,
    ),
}

FONT_SIZES: dict[str, FontSizeOption] = {
    "small": FontSizeOption(key="small", label="Small", root_px=15),
    "medium": FontSizeOption(key="medium", label="Medium (default)", root_px=17),
    "large": FontSizeOption(key="large", label="Large", root_px=19),
    "xlarge": FontSizeOption(key="xlarge", label="Extra large", root_px=21),
}

# fd2's "add new fonts" — scoped to long-form generated content only
# (topic reviews, paper summaries — the .prose-scholar styles in
# globals.css), not the app's own theme typography. Each theme keeps its
# own bespoke display/body fonts everywhere else; this is a separate,
# theme-independent axis, like font_size. "theme" is the no-op default —
# no [data-reading-font="theme"] CSS rule exists, so prose-scholar just
# inherits whatever the active theme already uses for body text.
READING_FONTS: dict[str, ReadingFontOption] = {
    "theme": ReadingFontOption(
        key="theme",
        label="Match theme (default)",
        description="Whatever the active theme already uses for body text.",
    ),
    "merriweather": ReadingFontOption(
        key="merriweather",
        label="Merriweather",
        description="A serif built for long-form on-screen reading.",
    ),
    "source_sans": ReadingFontOption(
        key="source_sans",
        label="Source Sans 3",
        description="A clean humanist sans for long-form reading.",
    ),
}

# Per-theme accent registry — only themes picked for the multi-hue accent
# treatment (fd3 backlog) get an entry here. soft_morning's own baseline
# --gold/--gold-dark (the "orange" values, see globals.css) is the
# implicit default and isn't repeated as an accent option; the other four
# are selected via the data-accent attribute layered on top of the theme.
THEME_ACCENTS: dict[str, dict[str, AccentOption]] = {
    "soft_morning": {
        "orange": AccentOption(key="orange", label="Orange", hex="#D9822E"),
        "rose": AccentOption(key="rose", label="Rose", hex="#D45C82"),
        "sage": AccentOption(key="sage", label="Sage", hex="#6B8F58"),
        "sky": AccentOption(key="sky", label="Sky", hex="#4A8FC2"),
        "lavender": AccentOption(key="lavender", label="Lavender", hex="#8570C9"),
    },
    "noir": {
        "cobalt": AccentOption(key="cobalt", label="Cobalt", hex="#3E7BFA"),
        "crimson": AccentOption(key="crimson", label="Crimson", hex="#F0455A"),
        "emerald": AccentOption(key="emerald", label="Emerald", hex="#2FBF71"),
        "violet": AccentOption(key="violet", label="Violet", hex="#A855F7"),
        "amber": AccentOption(key="amber", label="Amber", hex="#F5A623"),
    },
    "high_contrast": {
        "cyan": AccentOption(key="cyan", label="Cyan", hex="#00E5FF"),
        "orange": AccentOption(key="orange", label="Orange", hex="#FF8A00"),
        "magenta": AccentOption(key="magenta", label="Magenta", hex="#FF3EA5"),
        "violet": AccentOption(key="violet", label="Violet", hex="#B266FF"),
    },
}

DEFAULT_ACCENTS: dict[str, str] = {
    "soft_morning": "orange",
    "noir": "cobalt",
    "high_contrast": "cyan",
}

DEFAULT_DISPLAY_SETTINGS: dict[str, Any] = {
    "theme": "editorial",
    "font_size": "medium",
    "accent": None,
    "reading_font": "theme",
}


def list_accents(theme: str) -> list[dict[str, Any]]:
    accents = THEME_ACCENTS.get(theme, {})
    return [{"key": a.key, "label": a.label, "hex": a.hex} for a in accents.values()]


def list_themes() -> list[dict[str, Any]]:
    return [
        {
            "key": t.key,
            "label": t.label,
            "description": t.description,
            "dark": t.dark,
            "accents": list_accents(t.key),
        }
        for t in THEMES.values()
    ]


def list_font_sizes() -> list[dict[str, Any]]:
    return [
        {"key": f.key, "label": f.label, "root_px": f.root_px}
        for f in FONT_SIZES.values()
    ]


def list_reading_fonts() -> list[dict[str, Any]]:
    return [
        {"key": r.key, "label": r.label, "description": r.description}
        for r in READING_FONTS.values()
    ]


# ---------------------------------------------------------------------------
# Random — a meta-theme with no palette of its own. Deterministic, so no
# cron/scheduler or stored rotation state is needed: the ISO week number
# (Monday-anchored, UTC) is the clock, and CRC32 over a per-purpose key
# gives a stable-for-the-week, different-per-user pick.
# ---------------------------------------------------------------------------


def _week_hash(*parts: str, now: Optional[datetime] = None) -> int:
    now = now or datetime.utcnow()
    iso_year, iso_week, _ = now.isocalendar()
    key = ":".join([*parts, str(iso_year), str(iso_week)])
    return zlib.crc32(key.encode())


def resolve_random(user_id: str, now: Optional[datetime] = None) -> tuple[str, Optional[str]]:
    """
    What "random" resolves to for `user_id` this ISO week. Picks from every
    theme except random itself; if the picked theme has an accent pool,
    picks one of those too (independently seeded, so theme and accent
    don't always land on the same index).
    """
    pool = [key for key in THEMES if key != RANDOM_THEME_KEY]
    theme = pool[_week_hash(user_id, "theme", now=now) % len(pool)]

    accents = THEME_ACCENTS.get(theme)
    if not accents:
        return theme, None

    accent_keys = list(accents)
    accent = accent_keys[_week_hash(user_id, "accent", now=now) % len(accent_keys)]
    return theme, accent


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

    # accent only applies to themes registered in THEME_ACCENTS; themes
    # without a multi-hue treatment always normalize to None so a stale
    # accent doesn't survive a theme switch (e.g. soft_morning -> editorial).
    theme_accents = THEME_ACCENTS.get(theme)
    accent: Optional[str] = None
    if theme_accents:
        candidate = raw.get("accent")
        accent = candidate if candidate in theme_accents else DEFAULT_ACCENTS.get(theme)

    # reading_font is theme-independent (fd2) — no per-theme validity to
    # check, just a plain registry lookup.
    reading_font = str(raw.get("reading_font") or DEFAULT_DISPLAY_SETTINGS["reading_font"])
    if reading_font not in READING_FONTS:
        reading_font = DEFAULT_DISPLAY_SETTINGS["reading_font"]

    return {
        "theme": theme,
        "font_size": font_size,
        "accent": accent,
        "reading_font": reading_font,
    }


def _with_resolved(user_id: str, normalized: dict[str, Any]) -> dict[str, Any]:
    """
    Adds resolved_theme/resolved_accent — what should actually be painted
    (data-theme/data-accent) this week. Equal to theme/accent for every
    normal theme; computed via resolve_random() when theme == "random",
    so the frontend never has to special-case "random" itself.
    """
    if normalized["theme"] == RANDOM_THEME_KEY:
        resolved_theme, resolved_accent = resolve_random(user_id)
    else:
        resolved_theme, resolved_accent = normalized["theme"], normalized["accent"]
    return {**normalized, "resolved_theme": resolved_theme, "resolved_accent": resolved_accent}


def get_display_settings(user_id: str = DEFAULT_USER_ID) -> dict[str, Any]:
    """Read + normalize the display_settings blob for `user_id`."""
    settings = get_or_create_user_settings(user_id)
    normalized = ensure_settings_shape(settings.display_settings)
    return _with_resolved(user_id, normalized)


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
    return _with_resolved(user_id, normalized)
