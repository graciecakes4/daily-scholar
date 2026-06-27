"""
Scope library API (Phase E).

Endpoints for managing saved, shareable scopes:

  GET    /scopes/mine                         my owned + granted library
  GET    /scopes/search?q=                    public-scope search
  GET    /scopes/{id}                         view one (if allowed)
  POST   /scopes                              create
  PUT    /scopes/{id}                         update (owner only)
  DELETE /scopes/{id}                         delete (owner only)
  PUT    /scopes/{id}/visibility              flip public/private (owner only)
  POST   /scopes/{id}/fork                    fork into my library
  POST   /scopes/{id}/access-requests         request access to a private scope
  GET    /scopes/access-requests/incoming     requests targeted at scopes I own
  GET    /scopes/access-requests/outgoing     requests I've submitted
  POST   /scopes/access-requests/{id}/decide  owner: approve or deny

Plus, on the existing `scope_router` (mounted at /user):

  GET    /user/active-scope                   the full active Scope row
  PUT    /user/active-scope                   switch which scope is active

The legacy GET/PUT /user/scope endpoints in api/topics.py stay as the
back-compat shape for paper discovery; they read/write the
UserSettings.scope_mode + scope_topic_ids cache, which set_active keeps
in sync with the active Scope row.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..auth import get_current_user_id
from ..database import Scope, ScopeAccessRequest
from ..services import scopes as scope_service
from ..services.scopes import (
    AccessAlreadyGranted,
    AccessRequestDuplicate,
    AccessRequestError,
    AccessRequestNotFound,
    AccessRequestNotPending,
    ScopeError,
    ScopeNotEditable,
    ScopeNotFound,
    ScopeNotViewable,
    ScopeValidationError,
)


# =============================================================================
# Pydantic schemas
# =============================================================================


class ScopeOut(BaseModel):
    """Serialized Scope row."""
    id: int
    name: str
    description: Optional[str]
    owner_user_id: Optional[int]
    visibility: str
    scope_mode: str
    scope_topic_ids: list[str]
    forked_from_scope_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, s: Scope) -> "ScopeOut":
        return cls(
            id=s.id,
            name=s.name,
            description=s.description,
            owner_user_id=s.owner_user_id,
            visibility=s.visibility,
            scope_mode=s.scope_mode,
            scope_topic_ids=list(s.scope_topic_ids or []),
            forked_from_scope_id=s.forked_from_scope_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )


class LibraryItemOut(ScopeOut):
    """A scope from the caller's library, tagged with their relation to it."""
    # "owned" | "granted"
    relation: str


class ScopeCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    visibility: str = Field(default="private", pattern="^(private|public)$")
    scope_mode: str = Field(default="all", pattern="^(silo|multi|all)$")
    scope_topic_ids: list[str] = Field(default_factory=list)


class ScopeUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    visibility: Optional[str] = Field(default=None, pattern="^(private|public)$")
    scope_mode: Optional[str] = Field(default=None, pattern="^(silo|multi|all)$")
    scope_topic_ids: Optional[list[str]] = None


class VisibilityRequest(BaseModel):
    visibility: str = Field(..., pattern="^(private|public)$")


class ForkRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class AccessRequestCreate(BaseModel):
    message: Optional[str] = Field(default=None, max_length=2000)


class AccessRequestOut(BaseModel):
    id: int
    scope_id: int
    requester_user_id: str
    message: Optional[str]
    status: str
    created_at: datetime
    decided_at: Optional[datetime]
    decided_by_user_id: Optional[int]

    @classmethod
    def from_model(cls, r: ScopeAccessRequest) -> "AccessRequestOut":
        return cls(
            id=r.id,
            scope_id=r.scope_id,
            requester_user_id=r.requester_user_id,
            message=r.message,
            status=r.status,
            created_at=r.created_at,
            decided_at=r.decided_at,
            decided_by_user_id=r.decided_by_user_id,
        )


class DecideRequest(BaseModel):
    # "approve" or "deny" — explicit verb instead of a bool is friendlier
    # in audit logs and reduces "what does true mean" ambiguity
    decision: str = Field(..., pattern="^(approve|deny)$")


class ActiveScopeRequest(BaseModel):
    # null clears the active pointer and drops the user back onto the picker
    scope_id: Optional[int] = None


# =============================================================================
# Error translation
# =============================================================================


def _raise_for_service_error(exc: ScopeError) -> None:
    """Translate a service-layer exception into the right HTTP status."""
    if isinstance(exc, ScopeNotFound) or isinstance(exc, AccessRequestNotFound):
        raise HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ScopeNotViewable):
        # 404, not 403 — don't leak the existence of private scopes
        raise HTTPException(status_code=404, detail="scope not found")
    if isinstance(exc, ScopeNotEditable):
        raise HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ScopeValidationError):
        raise HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (AccessRequestDuplicate, AccessAlreadyGranted,
                        AccessRequestNotPending)):
        raise HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, AccessRequestError):
        raise HTTPException(status_code=400, detail=str(exc))
    # default for any unhandled ScopeError
    raise HTTPException(status_code=400, detail=str(exc))


# =============================================================================
# Routers
# =============================================================================


scopes_router = APIRouter(prefix="/scopes", tags=["Scopes"])

# the active-scope endpoints live on the same /user prefix as the legacy
# /user/scope shim, so they share a namespace in the OpenAPI doc
active_scope_router = APIRouter(prefix="/user", tags=["User"])


# ---------------------------------------------------------------------------
# Library + search
# ---------------------------------------------------------------------------


@scopes_router.get("/mine", response_model=list[LibraryItemOut])
def list_my_library(user_id: str = Depends(get_current_user_id)):
    """
    Scopes the caller owns plus private scopes they have a grant for.

    System (NULL-owner) scopes are NOT in this list — those surface via
    /scopes/search and the onboarding picker. Fork one to add it to
    your library.
    """
    items = scope_service.list_owned_and_granted(user_id)
    return [
        LibraryItemOut(
            **ScopeOut.from_model(s).model_dump(),
            relation=relation,
        )
        for s, relation in items
    ]


@scopes_router.get("/search", response_model=list[ScopeOut])
def search_public(
    q: Optional[str] = Query(default=None, description="name + description substring"),
    limit: int = Query(default=50, ge=1, le=200),
    user_id: str = Depends(get_current_user_id),
):
    """Public-scope search. Includes system-owned starter scopes."""
    rows = scope_service.search_public(user_id, query=q, limit=limit)
    return [ScopeOut.from_model(s) for s in rows]


# ---------------------------------------------------------------------------
# Access-request lifecycle (these MUST be declared before /{scope_id} routes
# so paths like "/access-requests/incoming" aren't swallowed by the catch-all)
# ---------------------------------------------------------------------------


@scopes_router.get(
    "/access-requests/incoming", response_model=list[AccessRequestOut],
)
def list_incoming_requests(
    status: Optional[str] = Query(
        default="pending",
        pattern="^(pending|approved|denied)$",
        description="filter by status; pass empty to get all",
    ),
    user_id: str = Depends(get_current_user_id),
):
    """Access requests targeted at scopes the caller owns. Defaults to pending."""
    rows = scope_service.list_incoming_requests(
        user_id, status=status or None
    )
    return [AccessRequestOut.from_model(r) for r in rows]


@scopes_router.get(
    "/access-requests/outgoing", response_model=list[AccessRequestOut],
)
def list_outgoing_requests(
    status: Optional[str] = Query(
        default=None,
        pattern="^(pending|approved|denied)$",
    ),
    user_id: str = Depends(get_current_user_id),
):
    """Access requests the caller has submitted, optionally filtered by status."""
    rows = scope_service.list_outgoing_requests(user_id, status=status)
    return [AccessRequestOut.from_model(r) for r in rows]


@scopes_router.post(
    "/access-requests/{request_id}/decide", response_model=AccessRequestOut,
)
def decide_access_request(
    request_id: int,
    body: DecideRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Owner-only: approve (insert grant) or deny a pending request."""
    try:
        req = scope_service.decide_request(
            user_id, request_id, approve=(body.decision == "approve"),
        )
    except ScopeError as e:
        _raise_for_service_error(e)
    return AccessRequestOut.from_model(req)


# ---------------------------------------------------------------------------
# Scope CRUD
# ---------------------------------------------------------------------------


@scopes_router.post("", response_model=ScopeOut, status_code=201)
def create_scope(
    body: ScopeCreateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Create a new scope owned by the caller."""
    try:
        s = scope_service.create_scope(
            user_id,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            scope_mode=body.scope_mode,
            scope_topic_ids=body.scope_topic_ids,
        )
    except ScopeError as e:
        _raise_for_service_error(e)
    return ScopeOut.from_model(s)


@scopes_router.get("/{scope_id}", response_model=ScopeOut)
def get_scope(scope_id: int, user_id: str = Depends(get_current_user_id)):
    """View one scope. 404 if not viewable (private + no grant)."""
    try:
        s = scope_service.get_scope(user_id, scope_id)
    except ScopeError as e:
        _raise_for_service_error(e)
    return ScopeOut.from_model(s)


@scopes_router.put("/{scope_id}", response_model=ScopeOut)
def update_scope(
    scope_id: int,
    body: ScopeUpdateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Patch editable fields. Owner / admin only."""
    try:
        s = scope_service.update_scope(
            user_id, scope_id,
            name=body.name,
            description=body.description,
            visibility=body.visibility,
            scope_mode=body.scope_mode,
            scope_topic_ids=body.scope_topic_ids,
        )
    except ScopeError as e:
        _raise_for_service_error(e)
    return ScopeOut.from_model(s)


@scopes_router.delete("/{scope_id}", status_code=204)
def delete_scope(scope_id: int, user_id: str = Depends(get_current_user_id)):
    """Hard-delete a scope. Owner / admin only. Cleanups in service layer."""
    try:
        scope_service.delete_scope(user_id, scope_id)
    except ScopeError as e:
        _raise_for_service_error(e)


@scopes_router.put("/{scope_id}/visibility", response_model=ScopeOut)
def set_visibility(
    scope_id: int,
    body: VisibilityRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Flip a scope between public and private. Owner / admin only."""
    try:
        s = scope_service.set_visibility(user_id, scope_id, body.visibility)
    except ScopeError as e:
        _raise_for_service_error(e)
    return ScopeOut.from_model(s)


@scopes_router.post("/{scope_id}/fork", response_model=ScopeOut, status_code=201)
def fork_scope(
    scope_id: int,
    body: Optional[ForkRequest] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Fork an accessible scope into the caller's library as a new private row."""
    body = body or ForkRequest()
    try:
        s = scope_service.fork_scope(
            user_id, scope_id, name=body.name, description=body.description,
        )
    except ScopeError as e:
        _raise_for_service_error(e)
    return ScopeOut.from_model(s)


@scopes_router.post(
    "/{scope_id}/access-requests", response_model=AccessRequestOut, status_code=201,
)
def request_access(
    scope_id: int,
    body: Optional[AccessRequestCreate] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Request view-access to a private scope."""
    body = body or AccessRequestCreate()
    try:
        req = scope_service.request_access(user_id, scope_id, message=body.message)
    except ScopeError as e:
        _raise_for_service_error(e)
    return AccessRequestOut.from_model(req)


# ---------------------------------------------------------------------------
# Active scope (on the /user namespace)
# ---------------------------------------------------------------------------


@active_scope_router.get("/active-scope", response_model=Optional[ScopeOut])
def get_active_scope(user_id: str = Depends(get_current_user_id)):
    """Return the caller's currently active Scope, or null if none picked yet."""
    s = scope_service.get_active(user_id)
    return ScopeOut.from_model(s) if s is not None else None


@active_scope_router.put("/active-scope", response_model=Optional[ScopeOut])
def set_active_scope(
    body: ActiveScopeRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Switch the caller's active scope. Pass {"scope_id": null} to clear
    (drops the user back onto the onboarding picker).

    Also updates the legacy UserSettings.scope_mode / scope_topic_ids
    cache so existing paper-discovery / quiz code that reads /user/scope
    sees the new mode without code changes.
    """
    try:
        scope_service.set_active(user_id, body.scope_id)
    except ScopeError as e:
        _raise_for_service_error(e)
    s = scope_service.get_active(user_id)
    return ScopeOut.from_model(s) if s is not None else None
