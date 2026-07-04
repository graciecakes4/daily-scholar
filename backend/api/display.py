"""
Display preferences API (Phase 5 / fd3, foundation slice).

Read/write the per-user display_settings blob (theme + font size), and
list the registries that drive the /settings/display picker UI. Same
shape as backend/api/notifications.py's settings endpoints, minus the
scheduler side effect (nothing to reload — the frontend applies the
theme/font-size attributes directly on save).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..auth import get_current_user_id
from ..services import display as display_svc

display_router = APIRouter(prefix="/display", tags=["Display"])


# ---------------------------------------------------------------------------
# pydantic schemas
# ---------------------------------------------------------------------------


class DisplaySettingsBody(BaseModel):
    """Full user display prefs blob — sent on every PUT (no PATCH semantics)."""

    theme: str = Field(default="editorial", description="Registry key from GET /display/themes.")
    font_size: str = Field(default="medium", description="Registry key from GET /display/font-sizes.")


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


@display_router.get("/themes")
def list_themes() -> dict[str, Any]:
    """Registry of available themes. Drives the theme picker."""
    return {"themes": display_svc.list_themes()}


@display_router.get("/font-sizes")
def list_font_sizes() -> dict[str, Any]:
    """Registry of available font sizes. Drives the font-size picker."""
    return {"font_sizes": display_svc.list_font_sizes()}


@display_router.get("/settings")
def get_settings(user_id: str = Depends(get_current_user_id)) -> dict[str, Any]:
    """Current display preferences for the calling user, fully populated."""
    return display_svc.get_display_settings(user_id)


@display_router.put("/settings")
def update_settings(
    body: DisplaySettingsBody,
    user_id: str = Depends(get_current_user_id),
) -> dict[str, Any]:
    """Replace this user's display preferences."""
    return display_svc.update_display_settings(user_id, body.model_dump())
