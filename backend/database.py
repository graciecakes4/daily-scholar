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
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session

Base = declarative_base()


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

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_topic_active_stream', 'active', 'stream'),
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
# DATABASE SETUP
# =============================================================================

_engine = None
_SessionLocal = None


def get_database_url() -> str:
    from .config import get_settings
    return get_settings().database_url


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            echo=False,
            connect_args={"check_same_thread": False}
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

    # seed user_stats row if absent
    session = get_session()
    try:
        stats = session.query(UserStats).first()
        if not stats:
            session.add(UserStats())
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

def get_seen_paper_ids() -> set[str]:
    """Get all unique IDs of papers the user has seen."""
    session = get_session()
    try:
        results = session.query(SeenPaper.unique_id).all()
        return {r[0] for r in results}
    finally:
        session.close()


def mark_paper_as_seen(paper_data: dict) -> SeenPaper:
    """Mark a paper as seen."""
    import json
    
    session = get_session()
    try:
        existing = session.query(SeenPaper).filter(
            SeenPaper.unique_id == paper_data.get("unique_id")
        ).first()
        
        if existing:
            return existing
        
        seen = SeenPaper(
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
        
        stats = session.query(UserStats).first()
        if stats:
            stats.total_papers_seen += 1
            stats.updated_at = datetime.utcnow()
        
        session.commit()
        return seen
    finally:
        session.close()


def update_user_streak():
    """Update the user's activity streak."""
    session = get_session()
    try:
        stats = session.query(UserStats).first()
        if not stats:
            return
        
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


def get_completed_topic_ids() -> set[str]:
    """Get topic_ids that the user has marked as completed."""
    session = get_session()
    try:
        results = session.query(ArchivedTopicReview.topic_id).filter(
            ArchivedTopicReview.status == "completed"
        ).all()
        return {r[0] for r in results}
    finally:
        session.close()


def get_review_later_topic_ids() -> set[str]:
    """Get topic_ids that the user has saved for later review."""
    session = get_session()
    try:
        results = session.query(ArchivedTopicReview.topic_id).filter(
            ArchivedTopicReview.status == "review_later"
        ).all()
        return {r[0] for r in results}
    finally:
        session.close()


def get_recently_reviewed_topic_ids(days: int = 3) -> set[str]:
    """Get topic_ids reviewed within the last N days (to avoid immediate repeats)."""
    session = get_session()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        results = session.query(ArchivedTopicReview.topic_id).filter(
            ArchivedTopicReview.last_reviewed_at >= cutoff
        ).all()
        return {r[0] for r in results}
    finally:
        session.close()


# =============================================================================
# TOPIC / SCOPE HELPERS
# =============================================================================

# sentinel for the default (pre-auth, local) user
DEFAULT_USER_ID = "__local__"


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


def get_active_topics(session: Optional[Session] = None) -> list[Topic]:
    """All active topics, ordered by descending weight then name."""
    own_session = session is None
    if own_session:
        session = get_session()
    try:
        return (
            session.query(Topic)
            .filter(Topic.active.is_(True))
            .order_by(Topic.weight.desc(), Topic.name.asc())
            .all()
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
    Falls back to 'all' if a silo/multi scope resolves to zero topics.
    """
    settings = get_or_create_user_settings(user_id)
    session = get_session()
    try:
        if settings.scope_mode == "silo" and settings.scope_topic_ids:
            topics = (
                session.query(Topic)
                .filter(
                    Topic.id == settings.scope_topic_ids[0],
                    Topic.active.is_(True),
                )
                .all()
            )
        elif settings.scope_mode == "multi" and settings.scope_topic_ids:
            topics = (
                session.query(Topic)
                .filter(
                    Topic.id.in_(settings.scope_topic_ids),
                    Topic.active.is_(True),
                )
                .order_by(Topic.weight.desc(), Topic.name.asc())
                .all()
            )
        else:
            topics = get_active_topics(session=session)

        # fallback: never return an empty list — discovery/review needs *something*
        if not topics:
            topics = get_active_topics(session=session)
        return topics
    finally:
        session.close()


if __name__ == "__main__":
    print("Creating database tables...")
    create_tables()
