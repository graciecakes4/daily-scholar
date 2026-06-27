"""
Scope library service (Phase E).

A scope is a saved, switchable view over the topics table. Each user
can own many scopes, share them publicly, request access to private
ones owned by other users, and fork accessible scopes into their own
library.

This module owns:
  * create / read / update / delete  with permission checks
  * public-scope search and "my library" listing
  * fork
  * access-request lifecycle (request -> owner approves/denies -> grant)
  * set / get the user's active scope

The endpoint layer wraps these functions and translates the typed
exceptions below into 4xx responses. The same exceptions are used by
the back-compat /user/scope shim.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import or_, and_
from sqlalchemy.orm import Session

from ..database import (
    DEFAULT_USER_ID,
    SCOPE_REQUEST_APPROVED,
    SCOPE_REQUEST_DENIED,
    SCOPE_REQUEST_PENDING,
    SCOPE_VISIBILITY_PRIVATE,
    SCOPE_VISIBILITY_PUBLIC,
    Scope,
    ScopeAccessGrant,
    ScopeAccessRequest,
    Topic,
    User,
    UserSettings,
    VALID_SCOPE_VISIBILITIES,
    get_or_create_user_settings,
    get_session,
)
from .topic_ownership import resolve_caller


log = logging.getLogger(__name__)


# allowed values for Scope.scope_mode
VALID_SCOPE_MODES = {"silo", "multi", "all"}

# soft cap on field sizes used in validation. database columns themselves
# are looser; these match what the UI displays comfortably.
MAX_NAME_LEN = 200
MAX_DESCRIPTION_LEN = 2000
MAX_TOPIC_IDS = 100


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


class ScopeError(ValueError):
    """Base class for scope-service failures."""


class ScopeNotFound(ScopeError):
    """No row with that scope id."""


class ScopeNotViewable(ScopeError):
    """Caller can't see this scope (private + not owner + no grant)."""


class ScopeNotEditable(ScopeError):
    """Caller can see the scope but is not its owner or an admin."""


class ScopeValidationError(ScopeError):
    """Body failed validation (mode, topic_ids, visibility, name)."""


class AccessRequestError(ScopeError):
    """Base class for access-request lifecycle failures."""


class AccessRequestNotFound(AccessRequestError):
    """No row with that request id."""


class AccessRequestNotPending(AccessRequestError):
    """Request has already been decided."""


class AccessRequestDuplicate(AccessRequestError):
    """A pending request from this user for this scope already exists."""


class AccessAlreadyGranted(AccessRequestError):
    """Caller already has view access to this scope (owner or prior grant)."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _normalize_topic_ids(topic_ids: Optional[Iterable[str]]) -> list[str]:
    """Dedupe + preserve order. None / falsy → []."""
    if not topic_ids:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for tid in topic_ids:
        if tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out


def _validate_scope_fields(
    name: Optional[str],
    description: Optional[str],
    visibility: Optional[str],
    scope_mode: Optional[str],
    scope_topic_ids: Optional[Iterable[str]],
    *,
    require_name: bool,
) -> None:
    """
    Shape check used by create + update. Mutating fields are all optional
    on update; set `require_name=True` for create.
    """
    if require_name or name is not None:
        if not name or not name.strip():
            raise ScopeValidationError("name is required and cannot be blank")
        if len(name) > MAX_NAME_LEN:
            raise ScopeValidationError(f"name exceeds {MAX_NAME_LEN} characters")

    if description is not None and len(description) > MAX_DESCRIPTION_LEN:
        raise ScopeValidationError(
            f"description exceeds {MAX_DESCRIPTION_LEN} characters"
        )

    if visibility is not None and visibility not in VALID_SCOPE_VISIBILITIES:
        raise ScopeValidationError(
            f"visibility must be one of {sorted(VALID_SCOPE_VISIBILITIES)}"
        )

    if scope_mode is not None and scope_mode not in VALID_SCOPE_MODES:
        raise ScopeValidationError(
            f"scope_mode must be one of {sorted(VALID_SCOPE_MODES)}"
        )

    if scope_topic_ids is not None:
        ids = list(scope_topic_ids)
        if len(ids) > MAX_TOPIC_IDS:
            raise ScopeValidationError(
                f"scope_topic_ids exceeds {MAX_TOPIC_IDS} entries"
            )

    # mode/topic-id consistency rules — same shape as the legacy
    # /user/scope endpoint enforced.
    if scope_mode == "silo":
        if scope_topic_ids is None or len(list(scope_topic_ids)) != 1:
            raise ScopeValidationError(
                "scope_mode='silo' requires exactly one topic id"
            )
    elif scope_mode == "multi":
        if not scope_topic_ids or len(list(scope_topic_ids)) == 0:
            raise ScopeValidationError(
                "scope_mode='multi' requires at least one topic id"
            )


def _check_topic_ids_exist(session: Session, topic_ids: list[str]) -> None:
    """Reject if any referenced topic id is missing from the topics table."""
    if not topic_ids:
        return
    rows = (
        session.query(Topic.id)
        .filter(Topic.id.in_(topic_ids))
        .all()
    )
    found = {r[0] for r in rows}
    missing = [tid for tid in topic_ids if tid not in found]
    if missing:
        raise ScopeValidationError(
            f"unknown topic id(s): {', '.join(missing)}"
        )


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------


def _has_grant(session: Session, scope_id: int, user_id_str: str) -> bool:
    return (
        session.query(ScopeAccessGrant)
        .filter(
            ScopeAccessGrant.scope_id == scope_id,
            ScopeAccessGrant.user_id == user_id_str,
        )
        .first()
        is not None
    )


def can_view_scope(
    session: Session,
    scope: Scope,
    user_id_str: str,
    caller: Optional[User],
    is_admin: bool,
) -> bool:
    """
    True if caller can read this scope.

      * system scope (owner is NULL)                 → everyone
      * public                                       → everyone
      * private, owner                               → yes
      * private, has ScopeAccessGrant                → yes
      * admin / solo (caller=None, is_admin=True)    → yes
      * everyone else                                → no
    """
    if scope.owner_user_id is None:
        return True
    if scope.visibility == SCOPE_VISIBILITY_PUBLIC:
        return True
    if is_admin:
        return True
    if caller is not None and scope.owner_user_id == caller.id:
        return True
    return _has_grant(session, scope.id, user_id_str)


def can_edit_scope(scope: Scope, caller: Optional[User], is_admin: bool) -> bool:
    """
      * admin / solo            → can edit anything
      * owner                   → can edit their own
      * grantees                → cannot (read-only — fork to change)
    """
    if is_admin:
        return True
    if scope.owner_user_id is None:
        return False
    return caller is not None and scope.owner_user_id == caller.id


def _require_view(
    session: Session,
    scope: Scope,
    user_id_str: str,
    caller: Optional[User],
    is_admin: bool,
) -> None:
    if not can_view_scope(session, scope, user_id_str, caller, is_admin):
        raise ScopeNotViewable(f"scope {scope.id} is not viewable by you")


def _require_edit(scope: Scope, caller: Optional[User], is_admin: bool) -> None:
    if not can_edit_scope(scope, caller, is_admin):
        raise ScopeNotEditable(f"scope {scope.id} is not editable by you")


def _default_owner_id(caller: Optional[User], is_admin: bool) -> Optional[int]:
    """
    On create: admins/solo default to system-owned (NULL); regular users
    default to themselves.
    """
    if is_admin and caller is None:
        # solo sentinel — create system scope
        return None
    if caller is None:
        # shouldn't happen at the endpoint layer
        return None
    return caller.id


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def create_scope(
    user_id_str: str,
    *,
    name: str,
    description: Optional[str] = None,
    visibility: str = SCOPE_VISIBILITY_PRIVATE,
    scope_mode: str = "all",
    scope_topic_ids: Optional[list[str]] = None,
    forked_from_scope_id: Optional[int] = None,
) -> Scope:
    """Insert a new scope owned by the caller (or system if admin/solo)."""
    topic_ids = _normalize_topic_ids(scope_topic_ids)
    _validate_scope_fields(
        name, description, visibility, scope_mode, topic_ids, require_name=True
    )

    session = get_session()
    try:
        caller, is_admin = resolve_caller(user_id_str)
        _check_topic_ids_exist(session, topic_ids)

        scope = Scope(
            name=name.strip(),
            description=description,
            owner_user_id=_default_owner_id(caller, is_admin),
            visibility=visibility,
            scope_mode=scope_mode,
            scope_topic_ids=topic_ids,
            forked_from_scope_id=forked_from_scope_id,
        )
        session.add(scope)
        session.commit()
        session.refresh(scope)
        return scope
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_scope(user_id_str: str, scope_id: int) -> Scope:
    """Fetch a scope by id, gated on view permission."""
    session = get_session()
    try:
        scope = session.get(Scope, scope_id)
        if scope is None:
            raise ScopeNotFound(f"scope {scope_id} not found")
        caller, is_admin = resolve_caller(user_id_str)
        _require_view(session, scope, user_id_str, caller, is_admin)
        # detach so the caller can read fields after we close the session
        session.expunge(scope)
        return scope
    finally:
        session.close()


def update_scope(
    user_id_str: str,
    scope_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    visibility: Optional[str] = None,
    scope_mode: Optional[str] = None,
    scope_topic_ids: Optional[list[str]] = None,
) -> Scope:
    """Patch the editable fields of a scope. Owner / admin only."""
    if scope_topic_ids is not None:
        scope_topic_ids = _normalize_topic_ids(scope_topic_ids)

    session = get_session()
    try:
        scope = session.get(Scope, scope_id)
        if scope is None:
            raise ScopeNotFound(f"scope {scope_id} not found")
        caller, is_admin = resolve_caller(user_id_str)
        _require_edit(scope, caller, is_admin)

        # validation uses the post-update state for mode/topic consistency
        next_mode = scope_mode if scope_mode is not None else scope.scope_mode
        next_topic_ids = (
            scope_topic_ids if scope_topic_ids is not None
            else list(scope.scope_topic_ids or [])
        )
        _validate_scope_fields(
            name, description, visibility, next_mode, next_topic_ids,
            require_name=False,
        )
        if scope_topic_ids is not None:
            _check_topic_ids_exist(session, scope_topic_ids)

        if name is not None:
            scope.name = name.strip()
        if description is not None:
            scope.description = description
        if visibility is not None:
            scope.visibility = visibility
        if scope_mode is not None:
            scope.scope_mode = scope_mode
        if scope_topic_ids is not None:
            scope.scope_topic_ids = scope_topic_ids

        session.commit()
        session.refresh(scope)
        session.expunge(scope)
        return scope
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def set_visibility(user_id_str: str, scope_id: int, visibility: str) -> Scope:
    """Convenience for the PUT /scopes/{id}/visibility endpoint."""
    return update_scope(user_id_str, scope_id, visibility=visibility)


def delete_scope(user_id_str: str, scope_id: int) -> None:
    """
    Hard-delete a scope. Owner / admin only.

    Cleanup is done explicitly in code rather than relying on the FK
    CASCADE / SET NULL clauses — SQLite doesn't enforce those unless
    PRAGMA foreign_keys is on, and per the topic_subscriptions
    convention we don't want to depend on dialect quirks. Behavior is
    identical to what the FK options would do under Postgres:

      * UserSettings rows pointing at this scope have active_scope_id
        cleared (so those users land on the onboarding picker)
      * Scopes that were forked FROM this one have forked_from_scope_id
        cleared (lineage breaks but the forks themselves survive)
      * ScopeAccessGrants and ScopeAccessRequests for this scope are
        deleted
      * The scope row itself is deleted
    """
    session = get_session()
    try:
        scope = session.get(Scope, scope_id)
        if scope is None:
            raise ScopeNotFound(f"scope {scope_id} not found")
        caller, is_admin = resolve_caller(user_id_str)
        _require_edit(scope, caller, is_admin)

        # clear active pointers
        (
            session.query(UserSettings)
            .filter(UserSettings.active_scope_id == scope.id)
            .update({"active_scope_id": None}, synchronize_session=False)
        )
        # break fork lineage on children
        (
            session.query(Scope)
            .filter(Scope.forked_from_scope_id == scope.id)
            .update({"forked_from_scope_id": None}, synchronize_session=False)
        )
        # drop grants + requests
        (
            session.query(ScopeAccessGrant)
            .filter(ScopeAccessGrant.scope_id == scope.id)
            .delete(synchronize_session=False)
        )
        (
            session.query(ScopeAccessRequest)
            .filter(ScopeAccessRequest.scope_id == scope.id)
            .delete(synchronize_session=False)
        )

        session.delete(scope)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Library + search
# ---------------------------------------------------------------------------


def list_owned_and_granted(user_id_str: str) -> list[tuple[Scope, str]]:
    """
    Library view: every scope the caller owns, plus every private scope
    they have a grant for. Each item is (Scope, relation) where relation
    is "owned" or "granted".

    System scopes are excluded — they show up in `search_public` and the
    onboarding picker, but aren't in any individual user's library until
    they fork.
    """
    session = get_session()
    try:
        caller, _is_admin = resolve_caller(user_id_str)

        owned: list[Scope] = []
        if caller is not None:
            owned = (
                session.query(Scope)
                .filter(Scope.owner_user_id == caller.id)
                .order_by(Scope.updated_at.desc())
                .all()
            )

        granted_ids = [
            r[0] for r in
            session.query(ScopeAccessGrant.scope_id)
            .filter(ScopeAccessGrant.user_id == user_id_str)
            .all()
        ]
        granted: list[Scope] = []
        if granted_ids:
            granted = (
                session.query(Scope)
                .filter(Scope.id.in_(granted_ids))
                .order_by(Scope.updated_at.desc())
                .all()
            )

        out: list[tuple[Scope, str]] = []
        for s in owned:
            session.expunge(s)
            out.append((s, "owned"))
        for s in granted:
            session.expunge(s)
            out.append((s, "granted"))
        return out
    finally:
        session.close()


def search_public(
    user_id_str: str,
    query: Optional[str] = None,
    limit: int = 50,
) -> list[Scope]:
    """
    Public-scope search by name + description substring. System scopes
    (NULL owner) are included; private scopes are not, even if the
    caller has a grant on one (those surface via list_owned_and_granted).

    Empty query returns the first `limit` public scopes by recency.
    """
    if limit <= 0 or limit > 200:
        limit = 50
    session = get_session()
    try:
        q = session.query(Scope).filter(
            Scope.visibility == SCOPE_VISIBILITY_PUBLIC
        )
        if query:
            like = f"%{query.strip()}%"
            q = q.filter(or_(Scope.name.ilike(like), Scope.description.ilike(like)))
        rows = q.order_by(Scope.updated_at.desc()).limit(limit).all()
        for s in rows:
            session.expunge(s)
        return rows
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Fork
# ---------------------------------------------------------------------------


def fork_scope(
    user_id_str: str,
    source_scope_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> Scope:
    """
    Copy a scope into the caller's library as a new private row, with
    forked_from_scope_id stamped. Source can be any scope the caller is
    allowed to view (public, system, owned, or granted).

    The fork starts private — the user can flip it to public from the
    library if they want. Name defaults to "Fork of <source.name>".
    """
    session = get_session()
    try:
        src = session.get(Scope, source_scope_id)
        if src is None:
            raise ScopeNotFound(f"scope {source_scope_id} not found")
        caller, is_admin = resolve_caller(user_id_str)
        _require_view(session, src, user_id_str, caller, is_admin)

        new_name = (name or f"Fork of {src.name}").strip()
        new_description = description if description is not None else src.description

        # validate the would-be new row up front so we don't insert junk
        topic_ids = _normalize_topic_ids(src.scope_topic_ids)
        _validate_scope_fields(
            new_name, new_description, SCOPE_VISIBILITY_PRIVATE,
            src.scope_mode, topic_ids, require_name=True,
        )

        fork = Scope(
            name=new_name,
            description=new_description,
            owner_user_id=_default_owner_id(caller, is_admin),
            visibility=SCOPE_VISIBILITY_PRIVATE,
            scope_mode=src.scope_mode,
            scope_topic_ids=topic_ids,
            forked_from_scope_id=src.id,
        )
        session.add(fork)
        session.commit()
        session.refresh(fork)
        session.expunge(fork)
        return fork
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Access requests
# ---------------------------------------------------------------------------


def request_access(
    user_id_str: str,
    scope_id: int,
    message: Optional[str] = None,
) -> ScopeAccessRequest:
    """
    Submit a request for view-access to a private scope.

      * scope must exist
      * scope must be private (public/system scopes are already viewable)
      * caller must not already be the owner
      * caller must not already have a grant
      * caller must not already have a pending request
    """
    session = get_session()
    try:
        scope = session.get(Scope, scope_id)
        if scope is None:
            raise ScopeNotFound(f"scope {scope_id} not found")
        if scope.visibility != SCOPE_VISIBILITY_PRIVATE:
            raise AccessRequestError(
                "scope is already accessible — public or system scope"
            )
        if scope.owner_user_id is None:
            raise AccessRequestError("system scopes do not accept access requests")

        caller, _is_admin = resolve_caller(user_id_str)
        if caller is not None and scope.owner_user_id == caller.id:
            raise AccessAlreadyGranted("you already own this scope")
        if _has_grant(session, scope.id, user_id_str):
            raise AccessAlreadyGranted("you already have view access to this scope")

        existing = (
            session.query(ScopeAccessRequest)
            .filter(
                ScopeAccessRequest.scope_id == scope.id,
                ScopeAccessRequest.requester_user_id == user_id_str,
                ScopeAccessRequest.status == SCOPE_REQUEST_PENDING,
            )
            .first()
        )
        if existing is not None:
            raise AccessRequestDuplicate(
                "a pending access request from you already exists for this scope"
            )

        req = ScopeAccessRequest(
            scope_id=scope.id,
            requester_user_id=user_id_str,
            message=message,
        )
        session.add(req)
        session.commit()
        session.refresh(req)
        session.expunge(req)
        return req
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def list_incoming_requests(
    user_id_str: str,
    *,
    status: Optional[str] = SCOPE_REQUEST_PENDING,
) -> list[ScopeAccessRequest]:
    """
    Requests targeted at scopes the caller owns. Defaults to pending;
    pass status=None for all.
    """
    session = get_session()
    try:
        caller, is_admin = resolve_caller(user_id_str)
        owned_scope_ids: list[int] = []
        if caller is not None:
            owned_scope_ids = [
                r[0] for r in
                session.query(Scope.id)
                .filter(Scope.owner_user_id == caller.id)
                .all()
            ]
        elif is_admin:
            # solo admin can see everything
            owned_scope_ids = [r[0] for r in session.query(Scope.id).all()]

        if not owned_scope_ids:
            return []

        q = session.query(ScopeAccessRequest).filter(
            ScopeAccessRequest.scope_id.in_(owned_scope_ids)
        )
        if status is not None:
            q = q.filter(ScopeAccessRequest.status == status)
        rows = q.order_by(ScopeAccessRequest.created_at.desc()).all()
        for r in rows:
            session.expunge(r)
        return rows
    finally:
        session.close()


def list_outgoing_requests(
    user_id_str: str,
    *,
    status: Optional[str] = None,
) -> list[ScopeAccessRequest]:
    """Requests the caller has submitted. Defaults to all statuses."""
    session = get_session()
    try:
        q = session.query(ScopeAccessRequest).filter(
            ScopeAccessRequest.requester_user_id == user_id_str
        )
        if status is not None:
            q = q.filter(ScopeAccessRequest.status == status)
        rows = q.order_by(ScopeAccessRequest.created_at.desc()).all()
        for r in rows:
            session.expunge(r)
        return rows
    finally:
        session.close()


def decide_request(
    user_id_str: str,
    request_id: int,
    *,
    approve: bool,
) -> ScopeAccessRequest:
    """
    Owner-only: approve or deny a pending access request.

    On approve: inserts a ScopeAccessGrant for the requester.
    On deny:    no grant; row is just stamped denied.
    """
    session = get_session()
    try:
        req = session.get(ScopeAccessRequest, request_id)
        if req is None:
            raise AccessRequestNotFound(f"request {request_id} not found")
        if req.status != SCOPE_REQUEST_PENDING:
            raise AccessRequestNotPending(
                f"request {request_id} is already {req.status}"
            )

        scope = session.get(Scope, req.scope_id)
        if scope is None:
            raise ScopeNotFound(f"scope {req.scope_id} not found")
        caller, is_admin = resolve_caller(user_id_str)
        _require_edit(scope, caller, is_admin)

        req.status = SCOPE_REQUEST_APPROVED if approve else SCOPE_REQUEST_DENIED
        req.decided_at = datetime.utcnow()
        req.decided_by_user_id = caller.id if caller is not None else None

        if approve:
            # idempotent: skip insert if a grant somehow already exists
            if not _has_grant(session, scope.id, req.requester_user_id):
                grant = ScopeAccessGrant(
                    scope_id=scope.id,
                    user_id=req.requester_user_id,
                    granted_by_user_id=caller.id if caller is not None else None,
                )
                session.add(grant)

        session.commit()
        session.refresh(req)
        session.expunge(req)
        return req
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Active scope
# ---------------------------------------------------------------------------


def set_active(user_id_str: str, scope_id: Optional[int]) -> UserSettings:
    """
    Point UserSettings.active_scope_id at `scope_id`. Pass None to clear
    (drops the user back onto the onboarding picker).

    Caller must be allowed to view the target scope.
    """
    session = get_session()
    try:
        if scope_id is not None:
            scope = session.get(Scope, scope_id)
            if scope is None:
                raise ScopeNotFound(f"scope {scope_id} not found")
            caller, is_admin = resolve_caller(user_id_str)
            _require_view(session, scope, user_id_str, caller, is_admin)

        settings = get_or_create_user_settings(user_id_str)
        # get_or_create_user_settings runs in its own session and commits.
        # re-fetch the row in this session to mutate it.
        settings = (
            session.query(UserSettings)
            .filter(UserSettings.user_id == user_id_str)
            .first()
        )
        settings.active_scope_id = scope_id
        # also refresh the legacy cache so /user/scope back-compat returns
        # the right shape until that endpoint is dropped.
        if scope_id is not None:
            target = session.get(Scope, scope_id)
            settings.scope_mode = target.scope_mode
            settings.scope_topic_ids = list(target.scope_topic_ids or [])
        session.commit()
        session.refresh(settings)
        session.expunge(settings)
        return settings
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_active(user_id_str: str) -> Optional[Scope]:
    """
    Return the user's currently active scope (or None if they haven't
    picked one yet).

    Used by:
      * GET /user/scope back-compat shim
      * paper discovery / quiz / review code that needs the scope_mode +
        scope_topic_ids of the active scope
    """
    session = get_session()
    try:
        settings = (
            session.query(UserSettings)
            .filter(UserSettings.user_id == user_id_str)
            .first()
        )
        if settings is None or settings.active_scope_id is None:
            return None
        scope = session.get(Scope, settings.active_scope_id)
        if scope is None:
            # active_scope_id points at a deleted row — SET NULL would
            # have caught it, but defensive in case of a race
            return None
        session.expunge(scope)
        return scope
    finally:
        session.close()
