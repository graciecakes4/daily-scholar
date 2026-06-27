"""
Database Models and Setup for Daily Scholar

Full paper lifecycle with:
- Seen paper tracking (avoid duplicates)
- Archived papers (user's saved papers)
- PDF file storage
- Topic/Quiz archives
- Topic completion tracking
"""

from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean,
    DateTime, Date, ForeignKey, JSON, create_engine, Index, UniqueConstraint,
    and_ as sa_and,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session

Base = declarative_base()

# sentinel for the default (pre-auth, local) user. real ids land when Cloudflare Access is enabled.
DEFAULT_USER_ID = "__local__"


# =============================================================================
# SEEN PAPERS - Track what user has been shown (avoid duplicates)
# =============================================================================

class SeenPaper(Base):
    """
    Tracks ALL papers shown to the user.
    This prevents showing the same paper twice.
    """
    __tablename__ = "seen_papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Owner — '__local__' sentinel today; real ids when Cloudflare Access lands
    user_id = Column(String(100), nullable=False, default="__local__", index=True)

    # Unique identifier (arxiv:xxx, doi:xxx, s2:xxx, or hash:xxx)
    unique_id = Column(String(200), unique=True, nullable=False, index=True)
    
    # Paper identifiers
    arxiv_id = Column(String(50), nullable=True)
    semantic_scholar_id = Column(String(100), nullable=True)
    doi = Column(String(100), nullable=True)
    
    # Basic metadata (for display in history)
    title = Column(String(500), nullable=False)
    authors = Column(Text)  # JSON string
    source = Column(String(50))  # "arxiv", "semantic_scholar", "core"
    url = Column(String(500))
    
    # When shown
    shown_date = Column(Date, nullable=False, default=date.today)
    shown_at = Column(DateTime, default=datetime.utcnow)
    
    # Was it archived?
    was_archived = Column(Boolean, default=False)
    
    __table_args__ = (
        Index('idx_seen_shown_date', 'shown_date'),
    )


# =============================================================================
# ARCHIVED PAPERS - Papers user explicitly saved
# =============================================================================

class ArchivedPaper(Base):
    """
    Papers the user has explicitly saved to their archive.
    """
    __tablename__ = "archived_papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="__local__", index=True)

    # Link to seen paper (if it came from daily discovery)
    seen_paper_id = Column(Integer, ForeignKey("seen_papers.id"), nullable=True)
    
    # Unique identifier
    unique_id = Column(String(200), unique=True, nullable=False, index=True)
    
    # Paper identifiers
    arxiv_id = Column(String(50), nullable=True)
    semantic_scholar_id = Column(String(100), nullable=True)
    doi = Column(String(100), nullable=True)
    
    # Paper metadata
    title = Column(String(500), nullable=False)
    authors = Column(Text)  # JSON string
    abstract = Column(Text)
    published_date = Column(String(50))
    source = Column(String(50))
    url = Column(String(500))
    pdf_url = Column(String(500))
    
    # Categorization
    primary_category = Column(String(100))
    categories = Column(JSON)
    relevance_score = Column(Float)
    
    # AI-generated content
    summary = Column(Text)
    key_findings = Column(JSON)
    
    # Local PDF storage
    local_pdf_path = Column(String(500), nullable=True)
    has_local_pdf = Column(Boolean, default=False)
    
    # User interaction
    user_rating = Column(Integer, nullable=True)
    user_notes = Column(Text, nullable=True)
    read_status = Column(String(20), default="unread")
    
    # Topic connections
    linked_topic_ids = Column(JSON)
    
    # Timestamps
    archived_at = Column(DateTime, default=datetime.utcnow)
    last_accessed_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_archived_status', 'read_status'),
        Index('idx_archived_date', 'archived_at'),
    )


# =============================================================================
# PDF FILES - Track uploaded/downloaded PDFs
# =============================================================================

class PaperPDF(Base):
    """
    Tracks PDF files stored locally.
    """
    __tablename__ = "paper_pdfs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="__local__", index=True)

    # Link to archived paper
    archived_paper_id = Column(Integer, ForeignKey("archived_papers.id"), nullable=True)
    
    # File info
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer)
    
    # Source
    source = Column(String(50))  # "upload", "download"
    source_url = Column(String(500), nullable=True)
    
    # Metadata
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Processing
    is_processed = Column(Boolean, default=False)
    extracted_text = Column(Text, nullable=True)


# =============================================================================
# ARCHIVED TOPIC REVIEWS
# =============================================================================

class ArchivedTopicReview(Base):
    """
    Topic reviews the user has completed.
    Status tracks the topic lifecycle:
      - 'active'       : default, topic is in the normal rotation pool
      - 'review_later' : user saved for later review, weighted higher in selection
      - 'completed'    : user marked as mastered, excluded from rotation
    """
    __tablename__ = "archived_topic_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="__local__", index=True)

    topic_id = Column(String(100), nullable=False, index=True)
    topic_name = Column(String(200), nullable=False)
    course_id = Column(String(100), nullable=False)
    course_name = Column(String(200), nullable=False)
    week_covered = Column(Integer)
    
    review_content = Column(Text)
    key_points = Column(JSON)
    connections = Column(JSON)
    practice_suggestions = Column(JSON)
    key_concepts = Column(JSON)
    
    user_notes = Column(Text, nullable=True)
    confidence_level = Column(Integer, nullable=True)
    review_count = Column(Integer, default=1)
    
    # NEW: Topic lifecycle status
    status = Column(String(20), default="active", nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    linked_paper_ids = Column(JSON)
    
    first_reviewed_at = Column(DateTime, default=datetime.utcnow)
    last_reviewed_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_topic_status', 'status'),
    )


# =============================================================================
# ARCHIVED QUIZZES
# =============================================================================

class ArchivedQuiz(Base):
    """
    Completed quizzes.
    """
    __tablename__ = "archived_quizzes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="__local__", index=True)

    topics = Column(JSON)
    topic_ids = Column(JSON)
    total_questions = Column(Integer)
    total_points = Column(Integer)
    score_earned = Column(Float)
    percentage = Column(Float)
    
    questions = Column(JSON)
    
    taken_at = Column(DateTime, default=datetime.utcnow)
    duration_seconds = Column(Integer, nullable=True)


# =============================================================================
# DAILY CONTENT CACHE
# =============================================================================

class DailyContentCache(Base):
    """
    Cache daily generated content to avoid regenerating.
    """
    __tablename__ = "daily_content_cache"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="__local__", index=True)

    # content_date is no longer unique on its own — (user_id, content_date) is.
    # Migration 0003 swaps the unique constraint.
    content_date = Column(Date, nullable=False, index=True)

    paper_unique_id = Column(String(200), nullable=True)
    paper_data = Column(JSON)
    paper_summary = Column(JSON)

    topic_reviews = Column(JSON)
    quiz_questions = Column(JSON)
    resources = Column(JSON)

    generated_at = Column(DateTime, default=datetime.utcnow)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "content_date", name="uq_daily_content_cache_user_date"),
    )


# =============================================================================
# USER STATS
# =============================================================================

class UserStats(Base):
    """
    Track user learning statistics.
    """
    __tablename__ = "user_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        String(100), nullable=False, default="__local__", index=True, unique=True
    )

    total_papers_seen = Column(Integer, default=0)
    total_papers_archived = Column(Integer, default=0)
    total_papers_completed = Column(Integer, default=0)
    total_topics_reviewed = Column(Integer, default=0)
    total_quizzes_taken = Column(Integer, default=0)
    total_quiz_questions = Column(Integer, default=0)
    total_correct_answers = Column(Integer, default=0)
    
    current_streak_days = Column(Integer, default=0)
    longest_streak_days = Column(Integer, default=0)
    last_activity_date = Column(Date, nullable=True)
    
    updated_at = Column(DateTime, default=datetime.utcnow)


# =============================================================================
# TOPICS - Unified topic model (replaces interests.yaml + courses.yaml)
# =============================================================================

class Topic(Base):
    """
    First-class topic entity that drives paper discovery AND review/quiz
    generation. Replaces the old split between interests (config/interests.yaml)
    and courses (config/courses.yaml).

    Loaded from config/topics/*.yaml on startup (one file per topic) and
    upserted into this table. The DB is canonical at runtime; YAML edits
    after the first bootstrap require an explicit POST /topics/import-yaml
    call to merge. UI edits write to this table only; POST /topics/export-yaml
    dumps the current DB state back to YAML files.
    """
    __tablename__ = "topics"

    # stable slug, used as primary key + foreign key from other tables
    id = Column(String(100), primary_key=True)

    # display
    name = Column(String(200), nullable=False)

    # grouping tag (e.g., "foundations", "photometric_classification")
    stream = Column(String(100), nullable=False, index=True)

    # quick on/off without deletion
    active = Column(Boolean, default=True, nullable=False, index=True)

    # boosts relevance scoring for paper discovery
    weight = Column(Float, default=1.0, nullable=False)

    # paper-discovery side (replaces interests.yaml content)
    keywords = Column(JSON, nullable=False, default=list)
    arxiv_categories = Column(JSON, nullable=False, default=list)
    recency_days = Column(Integer, default=30, nullable=False)
    min_relevance = Column(Float, default=0.18, nullable=False)

    # learning-content side (replaces courses.yaml topics)
    key_concepts = Column(JSON, nullable=False, default=list)
    learning_objectives = Column(JSON, nullable=False, default=list)
    resources = Column(JSON, nullable=False, default=list)
    quiz_difficulty = Column(String(20), default="medium", nullable=False)
    prerequisites = Column(JSON, nullable=False, default=list)

    # bookkeeping
    # "yaml" = bootstrapped from config/topics/<id>.yaml
    # "ui"   = created via the in-app editor (no YAML file unless exported)
    created_via = Column(String(20), default="yaml", nullable=False)

    # false means the YAML file is no longer on disk but the DB row is kept
    # (so UI-only topics aren't blown away when YAML files come and go)
    source_yaml_present = Column(Boolean, default=True, nullable=False)

    # ownership (Phase C of auth foundation):
    #   - NULL          → system topic; visible to everyone; only admins edit
    #   - users.id      → user-owned topic; visible per `visibility` rules
    # Existing yaml-bootstrapped topics get owner_user_id=NULL on backfill.
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    # "private" → only the owner (and admins) see this topic
    # "public"  → searchable + subscribable by other users (Phase D)
    # System topics default to "public" so the legacy global behavior is preserved.
    visibility = Column(String(20), default="private", nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_topic_active_stream', 'active', 'stream'),
        Index('idx_topic_owner_visibility', 'owner_user_id', 'visibility'),
    )


# =============================================================================
# USER SETTINGS - Per-user preferences (topic scope, etc.)
# =============================================================================

class UserSettings(Base):
    """
    Per-user settings. Today the only user is the local sentinel '__local__';
    when Cloudflare Access is flipped on, this table picks up real user_ids
    from the JWT claim with no schema change.

    The headline field is `scope_mode` + `scope_topic_ids`, which together
    define what subset of the topics table drives paper discovery, topic
    review, and quiz generation:
      - "silo"  : only the single topic_id in scope_topic_ids[0]
      - "multi" : explicit set in scope_topic_ids
      - "all"   : every Topic where active=True (scope_topic_ids ignored)
    """
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), unique=True, nullable=False, default="__local__", index=True)

    scope_mode = Column(String(20), default="all", nullable=False)
    scope_topic_ids = Column(JSON, nullable=False, default=list)

    # phase E (scope library): pointer to the row in `scopes` that drives
    # discovery / review / quizzes for this user. nullable so brand-new
    # users land on the onboarding picker before anything is active.
    # legacy scope_mode / scope_topic_ids above stay populated as a cache
    # for one release for back-compat with the /user/scope endpoint; the
    # migration script materializes them into a "My scope" row and points
    # active_scope_id at it.
    active_scope_id = Column(Integer, ForeignKey("scopes.id", ondelete="SET NULL"), nullable=True, index=True)

    # Notification preferences. Schema lives in backend/services/notifications.py
    # (DEFAULT_NOTIFICATION_SETTINGS). Stored as JSON so adding a new notification
    # type later is a registry change only — no migration needed.
    #
    # Shape:
    #   {
    #     "timezone": "America/New_York",     # IANA tz used for every cron trigger
    #     "types": {
    #         "study_reminder": {"enabled": bool, "cron": "M H * * DOW"},
    #         "paper_drop":     {"enabled": bool, "cron": "..."},
    #         "weekly_status":  {"enabled": bool, "cron": "..."},
    #         "quiz_nudge":     {"enabled": bool, "cron": "..."}
    #     }
    #   }
    notification_settings = Column(JSON, nullable=False, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# =============================================================================
# PUSH SUBSCRIPTIONS - Web Push (scaffolded for Phase 1)
# =============================================================================

class PushSubscription(Base):
    """
    Web Push subscriptions per the VAPID protocol. Populated by the
    POST /push/subscribe endpoint when a browser grants notification
    permission. Wired into actual push fanout during Phase 1 of the
    PWA migration; the schema lands now so we don't need a second
    migration later.
    """
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=False, default="__local__", index=True)

    # the three pieces of a Web Push subscription
    endpoint = Column(String(500), unique=True, nullable=False)
    p256dh = Column(String(200), nullable=False)
    auth = Column(String(200), nullable=False)

    # "ios" | "macos" | "android" | "desktop" | "unknown"
    platform = Column(String(50), default="unknown", nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_used_at = Column(DateTime, nullable=True)


# =============================================================================
# AUTH — Users and sessions (Phase A in-app auth foundation)
# =============================================================================


# Status / role enums kept as plain string columns so adding new values
# later is a no-op migration. Validation lives in the API layer.
USER_STATUS_PENDING = "pending"
USER_STATUS_ACTIVE = "active"
USER_STATUS_SUSPENDED = "suspended"
VALID_USER_STATUSES = {USER_STATUS_PENDING, USER_STATUS_ACTIVE, USER_STATUS_SUSPENDED}

USER_ROLE_USER = "user"
USER_ROLE_ADMIN = "admin"
VALID_USER_ROLES = {USER_ROLE_USER, USER_ROLE_ADMIN}


class User(Base):
    """
    A real human (or service) account.

    Two string identifiers, both unique:
      - `email`  : login credential. Always lowercased on write.
      - `user_id`: foreign-keyable identity string used in all the existing
                   user-scoped tables (seen_papers.user_id, etc.). Defaults
                   to email at signup; users can pick a custom handle as
                   long as it matches the format rules in
                   `auth_security.validate_user_id`. Locked at signup —
                   changing it later requires `scripts/reassign_user_id.py`
                   to migrate row ownership across the 9 user-scoped tables.

    The split lets users pick a privacy-preserving handle without us
    refactoring every existing `user_id VARCHAR(100)` column.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(200), unique=True, nullable=False, index=True)
    user_id = Column(String(100), unique=True, nullable=False, index=True)

    password_hash = Column(String(200), nullable=False)

    # "pending" → signed up but not approved (Phase B admin gate)
    # "active"  → can log in and use the app
    # "suspended" → can't log in; data preserved
    status = Column(String(20), nullable=False, default=USER_STATUS_PENDING)
    role = Column(String(20), nullable=False, default=USER_ROLE_USER)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)
    # self-referential FK so we know which admin approved which user.
    # Nullable because the bootstrap admin has nobody to approve them.
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    last_login_at = Column(DateTime, nullable=True)

    # Phase E: false until the user has completed (or skipped) the
    # onboarding wizard. Layout redirects to /onboarding when false.
    onboarded = Column(Boolean, default=False, nullable=False)

    # Per-tour version state. JSON map of {tour_id: highest_version_seen},
    # e.g. {"dashboard": 1, "scope": 1, "topics": 1}. Frontend has a
    # hardcoded TOUR_VERSION per tour; a tour fires when its stored
    # value is below the current version. Missing keys are treated as 0.
    # Server-side (not localStorage) for cross-device sync; JSON (not
    # one column per tour) so adding a new tour is just a new key.
    tour_state = Column(JSON, default=dict, nullable=False)


class InviteCode(Base):
    """
    Single- or multi-use signup invitation issued by an admin.

    The signup endpoint validates an incoming `invite_code` against this
    table: it must exist, not be revoked, not be expired, and `uses` must
    be below `max_uses`. On a successful signup we atomically increment
    `uses` and (when `uses` hits `max_uses`) stamp `redeemed_at` so the
    admin UI can render "used" vs "available" without recomputing from
    `uses`.

    `max_uses=1` codes (the default) are effectively single-use; setting
    `max_uses=N` lets an admin hand out one code to a small cohort.
    """
    __tablename__ = "invite_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # short urlsafe slug from secrets.token_urlsafe(9) — 12 chars,
    # ~70 bits of entropy; readable / phone-shareable
    code = Column(String(32), unique=True, nullable=False, index=True)

    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # null = never expires
    expires_at = Column(DateTime, nullable=True)

    max_uses = Column(Integer, default=1, nullable=False)
    uses = Column(Integer, default=0, nullable=False)

    # set when uses reaches max_uses (lets the UI render "used by" without
    # recomputing). Stamped to the most-recent redemption time.
    redeemed_at = Column(DateTime, nullable=True)
    # last user to redeem the code; useful for single-use code auditing
    last_redeemed_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # admin-set kill switch — separate from expiry so we can tell "rotated
    # out" from "naturally expired" in audit views
    revoked_at = Column(DateTime, nullable=True)


class AdminAuditEvent(Base):
    """
    Append-only log of admin mutations: who approved/rejected which user,
    who issued/revoked which invite code, who changed someone's role or
    status. Read-only after insert; nothing in the app deletes rows.

    Denormalized actor + target identifiers preserve display info even if
    the underlying user / invite row is later deleted. The FK columns
    `actor_user_id` (nullable) + `target_id` keep a best-effort link to
    live rows for querying; the `_string` / `_label` siblings keep the
    history readable forever.
    """
    __tablename__ = "admin_audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # "user.approve" | "user.reject" | "user.role_change"
    # "user.suspend" | "user.reactivate"
    # "invite.create" | "invite.revoke"
    event_type = Column(String(50), nullable=False, index=True)

    # actor — the admin who did the thing. NULL = solo `__local__` sentinel.
    # FK is nullable + ON DELETE SET NULL (Postgres); the denormalized
    # _string keeps the display name even after the row is gone.
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    actor_user_id_string = Column(String(100), nullable=False)

    # target — the user / invite that was acted on
    # "user" | "invite"
    target_type = Column(String(20), nullable=False)
    # the target's stable id (user.user_id string for users; invite_codes.code for invites)
    target_id = Column(String(200), nullable=True, index=True)
    # human-readable handle (email for users; code itself for invites) preserved
    # even if the target row gets deleted later
    target_label = Column(String(200), nullable=True)

    # flexible bag for before/after values and event-specific context
    # (e.g., {"old_role": "user", "new_role": "admin"})
    audit_metadata = Column("metadata", JSON, nullable=False, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("idx_admin_audit_created", "created_at"),
        Index("idx_admin_audit_event_created", "event_type", "created_at"),
    )


class TopicSubscription(Base):
    """
    A user's subscription to another user's public topic (Phase D).

    Subscriptions are "live" — when the owner edits the topic (keywords,
    name, etc.) the subscriber's paper discovery picks up the changes on
    the next query. The subscription row itself is just a (user, topic)
    pair; the FK reference does the heavy lifting.

    If the owner flips the topic from public → private, subscriptions
    persist but the topic disappears from subscribers' scope (the
    visibility filter rejects it). If they flip back to public, the
    subscription comes back to life. Hard-deleting the topic cleans up
    subscriptions explicitly (see topic_subscriptions.cleanup_subscriptions_for_topic).
    """
    __tablename__ = "topic_subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # subscriber identity — string user_id (email or custom handle), matches
    # the pattern used in the 9 other user-scoped tables
    user_id = Column(String(100), nullable=False, index=True)
    # which topic they subscribed to
    topic_id = Column(String(100), ForeignKey("topics.id"), nullable=False, index=True)
    subscribed_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_topic_subscriptions_user_topic"),
        Index("idx_topic_subscriptions_user", "user_id"),
    )


class Session(Base):
    """
    Server-side opaque session token. The cookie carries `token`; we look
    up the row, verify it isn't expired/revoked, and resolve to a user.

    Server-side (not JWT) so we can revoke instantly on logout / suspend
    without a denylist. The per-request DB lookup is cheap (indexed unique
    key) and worth the simplicity.
    """
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # urlsafe random; 64 chars = ~48 bytes of entropy. Indexed unique for
    # the per-request lookup.
    token = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)

    # captured at login for the session-list UI in a follow-up phase
    user_agent = Column(String(500), nullable=True)
    ip = Column(String(64), nullable=True)


# =============================================================================
# SCOPES — Saved, shareable views over the topics table (Phase E)
# =============================================================================
#
# TODO(post-beta): scope_access_grants.user_id + scope_access_requests
# .requester_user_id are kept as String(100) for consistency with the
# existing user-scoped tables (topic_subscriptions, seen_papers, ...).
# Once the broader String→Integer-FK migration of user-scoped tables
# lands, switch these two columns to Integer ForeignKey("users.id") in
# the same pass so the whole codebase is referentially consistent.
# Tracked in the post-beta tech-debt list.


SCOPE_VISIBILITY_PRIVATE = "private"
SCOPE_VISIBILITY_PUBLIC = "public"
VALID_SCOPE_VISIBILITIES = {SCOPE_VISIBILITY_PRIVATE, SCOPE_VISIBILITY_PUBLIC}

SCOPE_REQUEST_PENDING = "pending"
SCOPE_REQUEST_APPROVED = "approved"
SCOPE_REQUEST_DENIED = "denied"
VALID_SCOPE_REQUEST_STATUSES = {
    SCOPE_REQUEST_PENDING,
    SCOPE_REQUEST_APPROVED,
    SCOPE_REQUEST_DENIED,
}


class Scope(Base):
    """
    A named, switchable view over the topics table.

    A user can have many scopes in their library; exactly one is active
    at a time (UserSettings.active_scope_id). The active scope drives
    paper discovery, topic review, and quiz generation — the same role
    the legacy UserSettings.scope_mode / scope_topic_ids columns used to
    play directly.

    Ownership / visibility mirror the Topic model:
      - owner_user_id NULL  → system-seeded starter scope; visible to
        everyone, only admins edit
      - owner_user_id set, visibility="private" → only the owner (and
        anyone with a ScopeAccessGrant) can read
      - owner_user_id set, visibility="public"  → searchable + forkable
        by any logged-in user

    Forking copies the scope_mode + scope_topic_ids into a new row owned
    by the caller and stamps forked_from_scope_id at the source. Deleting
    the source SET NULLs forks rather than cascading so lineage doesn't
    disappear silently from a child.
    """
    __tablename__ = "scopes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    # null = system-seeded scope. otherwise the user who can edit it.
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    visibility = Column(String(20), default=SCOPE_VISIBILITY_PRIVATE, nullable=False, index=True)

    # selection semantics — same three modes as legacy UserSettings:
    #   "silo"  : exactly one topic id in scope_topic_ids[0]
    #   "multi" : explicit set in scope_topic_ids
    #   "all"   : every active topic the viewer can see (scope_topic_ids ignored)
    scope_mode = Column(String(20), default="all", nullable=False)
    scope_topic_ids = Column(JSON, nullable=False, default=list)

    # fork lineage. SET NULL on source delete so children persist.
    forked_from_scope_id = Column(
        Integer,
        ForeignKey("scopes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_scope_owner_visibility", "owner_user_id", "visibility"),
        Index("idx_scope_visibility_name", "visibility", "name"),
    )


class ScopeAccessGrant(Base):
    """
    Records that a specific user has been granted view-access to a
    private scope. One row per (scope, user). Typically created when an
    owner approves a ScopeAccessRequest; can also be inserted directly
    by an admin tool.

    Grants are not the same as ownership — a grantee can read and fork
    but not edit or delete the original.
    """
    __tablename__ = "scope_access_grants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_id = Column(
        Integer,
        ForeignKey("scopes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # string user_id (email or custom handle), matching the convention used
    # in the other user-scoped tables (seen_papers, topic_subscriptions, ...)
    user_id = Column(String(100), nullable=False, index=True)
    granted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    granted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        UniqueConstraint("scope_id", "user_id", name="uq_scope_access_grants_scope_user"),
        Index("idx_scope_access_grants_user", "user_id"),
    )


class ScopeAccessRequest(Base):
    """
    A request from a user to view a private scope.

    Flow:
      1. requester POSTs /scopes/{id}/access-requests with an optional
         message → row inserted with status="pending"
      2. owner sees it in their /scopes/access-requests/incoming inbox
      3. owner decides → status="approved" + ScopeAccessGrant inserted,
         or status="denied"; decided_at + decided_by_user_id stamped

    There may be at most one row in "pending" state per (scope,
    requester) pair; once denied a requester can submit again. The
    invariant is enforced in the service layer, not the DB, so the
    history of past denied requests is preserved.
    """
    __tablename__ = "scope_access_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope_id = Column(
        Integer,
        ForeignKey("scopes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requester_user_id = Column(String(100), nullable=False, index=True)
    message = Column(Text, nullable=True)

    status = Column(String(20), default=SCOPE_REQUEST_PENDING, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at = Column(DateTime, nullable=True)
    decided_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        Index("idx_scope_access_requests_scope_status", "scope_id", "status"),
        Index("idx_scope_access_requests_requester_status", "requester_user_id", "status"),
    )


# =============================================================================
# DATABASE SETUP
# =============================================================================

_engine = None
_SessionLocal = None


def get_database_url() -> str:
    """
    Return the configured DB URL, normalized to a SQLAlchemy-friendly driver.

    Railway / Heroku / many other Postgres providers inject URLs like
    `postgres://user:pass@host/db`. SQLAlchemy needs an explicit driver name
    in the scheme (`postgresql+psycopg://...`). This shim rewrites the prefix
    so the same DATABASE_URL works on every host without per-platform tweaks.
    """
    from .config import get_settings
    url = get_settings().database_url
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://") and "+" not in url.split("://", 1)[0]:
        # bare `postgresql://` defaults to psycopg2; force psycopg v3
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def get_engine():
    global _engine
    if _engine is None:
        url = get_database_url()
        # `check_same_thread=False` is a SQLite-only connect arg; psycopg rejects it.
        # SQLAlchemy URLs look like 'sqlite:///...', 'sqlite+aiosqlite:///...',
        # 'postgresql+psycopg://...', etc.
        connect_args: dict = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(
            url,
            echo=False,
            connect_args=connect_args,
            pool_pre_ping=True,  # cheap health-check on each checkout; avoids stale conns
        )
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal()


def create_tables():
    """
    Bring the database up to the latest schema via Alembic.

    Handles four scenarios:
      1. Fresh install (no tables): runs all migrations from scratch.
      2. Pre-alembic legacy install (app tables exist, no alembic_version
         table): backfills any columns missing from the old runtime
         migration, stamps the DB at baseline, then upgrades.
      3. Failed prior upgrade (alembic_version table exists but is empty
         because the first attempt errored before stamping): treated as
         legacy — backfill, stamp, upgrade.
      4. Already-managed install (alembic_version has a revision): just
         upgrades to head.

    Also creates the data directory and seeds an initial UserStats row.
    """
    from pathlib import Path
    from sqlalchemy import inspect, text

    db_path = Path("./data")
    db_path.mkdir(parents=True, exist_ok=True)
    papers_path = Path("./data/papers")
    papers_path.mkdir(parents=True, exist_ok=True)

    engine = get_engine()
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    has_legacy_tables = "user_stats" in existing_tables

    # read the actual revision out of alembic_version (table can exist but
    # be empty if a previous upgrade failed before stamping)
    current_revision: Optional[str] = None
    if "alembic_version" in existing_tables:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
            if row is not None:
                current_revision = row[0]

    if current_revision is not None:
        # fully managed — just upgrade
        _run_alembic("upgrade", "head")
    elif has_legacy_tables:
        # legacy DB (with or without an empty alembic_version table)
        _backfill_legacy_columns(engine)
        _run_alembic("stamp", "0001_baseline")
        _run_alembic("upgrade", "head")
    else:
        # fresh install — alembic creates everything
        _run_alembic("upgrade", "head")

    # seed user_stats row for the local sentinel user if absent
    session = get_session()
    try:
        stats = session.query(UserStats).filter(
            UserStats.user_id == DEFAULT_USER_ID
        ).first()
        if not stats:
            session.add(UserStats(user_id=DEFAULT_USER_ID))
            session.commit()
    finally:
        session.close()

    print("✅ Database schema is up to date.")
    return engine


def _run_alembic(action: str, revision: str):
    """Invoke alembic programmatically using the project's alembic.ini."""
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", get_database_url())

    if action == "upgrade":
        command.upgrade(cfg, revision)
    elif action == "stamp":
        command.stamp(cfg, revision)
    else:
        raise ValueError(f"unknown alembic action: {action}")


def _backfill_legacy_columns(engine):
    """
    Pre-alembic Daily Scholar applied a manual ALTER TABLE at runtime to
    add 'status' and 'completed_at' columns on archived_topic_reviews. If a
    beta-tester DB predates that migration, replay it here so stamping
    baseline reflects reality.
    """
    from sqlalchemy import text, inspect

    inspector = inspect(engine)
    if "archived_topic_reviews" not in set(inspector.get_table_names()):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("archived_topic_reviews")}
    with engine.connect() as conn:
        if "status" not in existing_columns:
            conn.execute(text(
                "ALTER TABLE archived_topic_reviews "
                "ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"
            ))
            print("  ↳ Backfilled: archived_topic_reviews.status")
        if "completed_at" not in existing_columns:
            conn.execute(text(
                "ALTER TABLE archived_topic_reviews "
                "ADD COLUMN completed_at DATETIME"
            ))
            print("  ↳ Backfilled: archived_topic_reviews.completed_at")
        conn.commit()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_seen_paper_ids(user_id: str = DEFAULT_USER_ID) -> set[str]:
    """Get all unique IDs of papers this user has seen."""
    session = get_session()
    try:
        results = session.query(SeenPaper.unique_id).filter(
            SeenPaper.user_id == user_id
        ).all()
        return {r[0] for r in results}
    finally:
        session.close()


def mark_paper_as_seen(paper_data: dict, user_id: str = DEFAULT_USER_ID) -> SeenPaper:
    """Mark a paper as seen for this user."""
    import json

    session = get_session()
    try:
        # unique_id is globally unique, so we scope existence checks per-user
        existing = session.query(SeenPaper).filter(
            SeenPaper.unique_id == paper_data.get("unique_id"),
            SeenPaper.user_id == user_id,
        ).first()

        if existing:
            return existing

        seen = SeenPaper(
            user_id=user_id,
            unique_id=paper_data.get("unique_id"),
            arxiv_id=paper_data.get("arxiv_id"),
            semantic_scholar_id=paper_data.get("semantic_scholar_id"),
            doi=paper_data.get("doi"),
            title=paper_data.get("title"),
            authors=json.dumps(paper_data.get("authors", [])),
            source=paper_data.get("source"),
            url=paper_data.get("url"),
            shown_date=date.today(),
        )
        session.add(seen)

        # auto-create the stats row for first-time users so the counter sticks
        stats = get_or_create_user_stats(user_id, session=session)
        stats.total_papers_seen += 1
        stats.updated_at = datetime.utcnow()

        session.commit()
        return seen
    finally:
        session.close()


def get_or_create_user_stats(user_id: str, session: Optional[Session] = None) -> UserStats:
    """
    Fetch the UserStats row for this user, creating a zeroed one if absent.

    Without this, counters silently stay at 0 for any user_id other than the
    `__local__` sentinel (the only row seeded by create_tables). When a CF
    Access identity first hits an archive endpoint, the stats row needs to
    exist before we can increment it.

    Pass an existing session to participate in its transaction; otherwise we
    open and close our own.
    """
    own_session = session is None
    if own_session:
        session = get_session()
    try:
        stats = session.query(UserStats).filter(
            UserStats.user_id == user_id
        ).first()
        if stats is None:
            stats = UserStats(user_id=user_id)
            session.add(stats)
            session.commit()
            session.refresh(stats)
        return stats
    finally:
        if own_session:
            session.close()


def update_user_streak(user_id: str = DEFAULT_USER_ID):
    """Update this user's activity streak. Creates the stats row if absent."""
    session = get_session()
    try:
        stats = get_or_create_user_stats(user_id, session=session)

        today = date.today()

        if stats.last_activity_date is None:
            stats.current_streak_days = 1
        elif stats.last_activity_date == today:
            pass
        elif stats.last_activity_date == today - timedelta(days=1):
            stats.current_streak_days += 1
        else:
            stats.current_streak_days = 1

        stats.last_activity_date = today
        stats.longest_streak_days = max(stats.longest_streak_days, stats.current_streak_days)
        stats.updated_at = datetime.utcnow()

        session.commit()
    finally:
        session.close()


def get_completed_topic_ids(user_id: str = DEFAULT_USER_ID) -> set[str]:
    """Get topic_ids that this user has marked as completed."""
    session = get_session()
    try:
        results = session.query(ArchivedTopicReview.topic_id).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.status == "completed",
        ).all()
        return {r[0] for r in results}
    finally:
        session.close()


def get_review_later_topic_ids(user_id: str = DEFAULT_USER_ID) -> set[str]:
    """Get topic_ids that this user has saved for later review."""
    session = get_session()
    try:
        results = session.query(ArchivedTopicReview.topic_id).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.status == "review_later",
        ).all()
        return {r[0] for r in results}
    finally:
        session.close()


def get_recently_reviewed_topic_ids(user_id: str = DEFAULT_USER_ID, days: int = 3) -> set[str]:
    """Get topic_ids reviewed within the last N days (to avoid immediate repeats)."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        results = session.query(ArchivedTopicReview.topic_id).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.last_reviewed_at >= cutoff,
        ).all()
        return {r[0] for r in results}
    finally:
        session.close()


# =============================================================================
# TOPIC / SCOPE HELPERS
# =============================================================================


def get_or_create_user_settings(user_id: str = DEFAULT_USER_ID) -> UserSettings:
    """
    Fetch the UserSettings row for this user, creating a default one if it
    doesn't yet exist. Default scope is 'all' (every active topic).
    """
    session = get_session()
    try:
        settings = session.query(UserSettings).filter(
            UserSettings.user_id == user_id
        ).first()
        if settings is None:
            settings = UserSettings(user_id=user_id, scope_mode="all", scope_topic_ids=[])
            session.add(settings)
            session.commit()
            session.refresh(settings)
        return settings
    finally:
        session.close()


def _apply_visibility_filter(query, user_id: str):
    """
    Limit a Topic query to rows the caller can see in *scope* — i.e.,
    topics that should drive paper discovery, daily content, and quiz.
    Phase D changed the third bucket from "any public" to "public AND
    subscribed", so users explicitly opt in to following other people's
    topics via the Discover page.

    Rules (mirrors services/topic_ownership.can_view_topic for the
    scope-vs-browse split):
      * solo `__local__` (admin sentinel) → no filter applied
      * admin user → no filter applied
      * regular user → system (NULL owner) OR own OR (public AND subscribed)

    Imports are lazy to dodge the circular auth → database → auth and
    topic_subscriptions → database → topic_subscriptions cycles at
    module load.
    """
    if user_id == DEFAULT_USER_ID:
        return query
    # local imports to dodge circular load order
    from sqlalchemy import or_
    from .auth import lookup_user_by_user_id
    from .services.topic_subscriptions import list_subscribed_topic_ids

    user = lookup_user_by_user_id(user_id)
    if user is not None and user.role == "admin":
        return query

    clauses = [Topic.owner_user_id.is_(None)]
    if user is not None:
        clauses.append(Topic.owner_user_id == user.id)

    # subscribed-and-still-public topics. If the owner flipped their
    # topic private after the subscription, we keep the subscription row
    # but filter it out here — owner control wins over follower history.
    sub_ids = list_subscribed_topic_ids(user_id)
    if sub_ids:
        clauses.append(
            sa_and(Topic.id.in_(sub_ids), Topic.visibility == "public")
        )

    return query.filter(or_(*clauses))


def get_active_topics(
    session: Optional[Session] = None,
    *,
    user_id: str = DEFAULT_USER_ID,
) -> list[Topic]:
    """
    All active topics the caller is allowed to see, ordered by descending
    weight then name.

    The `user_id` parameter applies the same ownership filter that the
    /topics endpoints use, so paper discovery / review / quiz only see
    topics this user actually has rights to.
    """
    own_session = session is None
    if own_session:
        session = get_session()
    try:
        q = session.query(Topic).filter(Topic.active.is_(True))
        q = _apply_visibility_filter(q, user_id)
        return (
            q.order_by(Topic.weight.desc(), Topic.name.asc()).all()
        )
    finally:
        if own_session:
            session.close()


def get_topics_for_scope(user_id: str = DEFAULT_USER_ID) -> list[Topic]:
    """
    Resolve the user's topic scope into the actual list of Topic rows that
    paper discovery, topic review, and quiz generation should operate on.

    Behavior:
      - 'silo'  : the single topic id in scope_topic_ids[0], if active
      - 'multi' : every topic in scope_topic_ids whose row is active
      - 'all'   : every active topic (default)
    All branches also apply the Phase C ownership filter — a user can't
    scope to a topic they can't see.
    Falls back to 'all' if a silo/multi scope resolves to zero topics.
    """
    settings = get_or_create_user_settings(user_id)
    session = get_session()
    try:
        if settings.scope_mode == "silo" and settings.scope_topic_ids:
            q = session.query(Topic).filter(
                Topic.id == settings.scope_topic_ids[0],
                Topic.active.is_(True),
            )
            topics = _apply_visibility_filter(q, user_id).all()
        elif settings.scope_mode == "multi" and settings.scope_topic_ids:
            q = session.query(Topic).filter(
                Topic.id.in_(settings.scope_topic_ids),
                Topic.active.is_(True),
            ).order_by(Topic.weight.desc(), Topic.name.asc())
            topics = _apply_visibility_filter(q, user_id).all()
        else:
            topics = get_active_topics(session=session, user_id=user_id)

        # fallback: never return an empty list — discovery/review needs *something*
        if not topics:
            topics = get_active_topics(session=session, user_id=user_id)
        return topics
    finally:
        session.close()


if __name__ == "__main__":
    print("Creating database tables...")
    create_tables()
