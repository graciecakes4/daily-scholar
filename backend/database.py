"""
Database Models and Setup for Daily Scholar

This module defines the SQLite database schema using SQLAlchemy ORM.
We use SQLite because it's:
- Simple (just a file, no server to manage)
- Perfect for single-user applications
- Easy to backup (just copy the file)

LEARNING NOTES:
- SQLAlchemy ORM maps Python classes to database tables
- Each class attribute becomes a column
- Relationships link tables together (like foreign keys)
- Async support lets us handle multiple requests efficiently
"""

from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Text, Float, Boolean, 
    DateTime, Date, ForeignKey, JSON, create_engine
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Base class for all our models
Base = declarative_base()


# =============================================================================
# PAPER TRACKING
# =============================================================================

class SeenPaper(Base):
    """
    Tracks papers that have been shown to the user.
    
    This prevents showing the same paper twice and helps us
    understand what topics the user has been exposed to.
    """
    __tablename__ = "seen_papers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Paper identifiers (different sources use different IDs)
    arxiv_id = Column(String(50), unique=True, nullable=True)
    semantic_scholar_id = Column(String(100), unique=True, nullable=True)
    doi = Column(String(100), unique=True, nullable=True)
    
    # Paper metadata
    title = Column(String(500), nullable=False)
    authors = Column(Text)  # JSON string of author names
    abstract = Column(Text)
    published_date = Column(Date)
    source = Column(String(50))  # "arxiv", "semantic_scholar", "core"
    url = Column(String(500))
    pdf_url = Column(String(500))
    
    # Our categorization
    primary_category = Column(String(100))  # e.g., "Machine Learning"
    relevance_score = Column(Float)  # 0-1 score of how relevant to interests
    
    # When we showed it
    shown_date = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # User interaction
    user_rating = Column(Integer, nullable=True)  # 1-5 stars
    user_notes = Column(Text, nullable=True)
    bookmarked = Column(Boolean, default=False)


class DailyContent(Base):
    """
    Stores the generated daily content package.
    
    Each day, we generate a complete "learning package" with:
    - Selected paper
    - Topic reviews
    - Quiz questions
    
    This lets us cache the content and not regenerate it.
    """
    __tablename__ = "daily_content"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    content_date = Column(Date, unique=True, nullable=False)
    
    # Selected paper for the day
    paper_id = Column(Integer, ForeignKey("seen_papers.id"))
    paper = relationship("SeenPaper")
    
    # Generated content (stored as JSON)
    paper_summary = Column(Text)  # AI-generated summary
    topic_reviews = Column(JSON)  # List of topic review content
    quiz_questions = Column(JSON)  # List of quiz questions
    supplementary_resources = Column(JSON)  # Additional links/resources
    
    # Generation metadata
    generated_at = Column(DateTime, default=datetime.utcnow)
    generation_model = Column(String(50))  # Which Claude model was used
    
    # User interaction
    completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)


# =============================================================================
# QUIZ & PROGRESS TRACKING
# =============================================================================

class QuizAttempt(Base):
    """
    Records each quiz attempt and the user's answers.
    
    This data feeds into the spaced repetition algorithm
    to determine which topics need more review.
    """
    __tablename__ = "quiz_attempts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # When the quiz was taken
    attempt_date = Column(DateTime, default=datetime.utcnow)
    
    # Link to daily content if part of daily quiz
    daily_content_id = Column(Integer, ForeignKey("daily_content.id"), nullable=True)
    
    # Quiz details
    topic_id = Column(String(100), nullable=False)  # From courses.yaml
    course_id = Column(String(100), nullable=False)
    question_type = Column(String(50))  # "multiple_choice", "short_answer", etc.
    
    # The actual Q&A
    question_text = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    user_answer = Column(Text)
    
    # Scoring
    is_correct = Column(Boolean)
    score = Column(Float)  # 0-1 for partial credit
    
    # For review
    explanation = Column(Text)  # Why the answer is correct
    time_taken_seconds = Column(Integer)  # How long user took to answer


class TopicProgress(Base):
    """
    Tracks learning progress for each topic.
    
    Used by the spaced repetition algorithm to schedule reviews.
    """
    __tablename__ = "topic_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Topic identification
    topic_id = Column(String(100), nullable=False, unique=True)
    course_id = Column(String(100), nullable=False)
    
    # Spaced repetition data
    times_reviewed = Column(Integer, default=0)
    times_correct = Column(Integer, default=0)
    current_interval_days = Column(Float, default=1.0)  # Days until next review
    ease_factor = Column(Float, default=2.5)  # Multiplier for intervals
    
    # Scheduling
    last_reviewed = Column(DateTime, nullable=True)
    next_review_date = Column(Date, nullable=True)
    
    # Performance metrics
    average_score = Column(Float, default=0.0)
    streak = Column(Integer, default=0)  # Consecutive correct answers
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =============================================================================
# FILE UPLOADS
# =============================================================================

class UploadedFile(Base):
    """
    Tracks files uploaded for course materials.
    """
    __tablename__ = "uploaded_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # File info
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    file_path = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer)
    mime_type = Column(String(100))
    
    # Categorization
    course_id = Column(String(100), nullable=True)
    topic_id = Column(String(100), nullable=True)
    file_type = Column(String(50))  # "lecture", "notes", "homework", "other"
    
    # Processing status
    processed = Column(Boolean, default=False)
    extracted_text = Column(Text, nullable=True)
    
    # Metadata
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    description = Column(Text, nullable=True)


# =============================================================================
# DATABASE SETUP
# =============================================================================

def get_database_url(async_mode: bool = True) -> str:
    """
    Get the database URL, optionally configured for async.
    
    SQLite URLs need to be different for sync vs async:
    - Sync: sqlite:///./data/daily_scholar.db
    - Async: sqlite+aiosqlite:///./data/daily_scholar.db
    """
    from .config import get_settings
    
    base_url = get_settings().database_url
    
    if async_mode and "sqlite" in base_url and "aiosqlite" not in base_url:
        return base_url.replace("sqlite:", "sqlite+aiosqlite:")
    
    return base_url


def create_tables():
    """
    Create all database tables.
    
    Run this once during setup, or call it on app startup
    to ensure tables exist.
    """
    from pathlib import Path
    
    # Ensure data directory exists
    db_path = Path("./data")
    db_path.mkdir(parents=True, exist_ok=True)
    
    # Create sync engine for table creation
    engine = create_engine(
        get_database_url(async_mode=False),
        echo=True  # Set to False in production
    )
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    print("✅ Database tables created successfully!")
    return engine


# Async session factory (used in FastAPI)
async def get_async_engine():
    """Create an async database engine."""
    return create_async_engine(
        get_database_url(async_mode=True),
        echo=True  # Set to False in production
    )


async def get_async_session():
    """
    Dependency that provides a database session.
    
    Usage in FastAPI:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_async_session)):
            ...
    """
    engine = await get_async_engine()
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session


# =============================================================================
# QUICK TESTING
# =============================================================================

if __name__ == "__main__":
    # Quick test: create tables
    print("Creating database tables...")
    create_tables()
