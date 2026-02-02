"""
Pydantic Models for Daily Scholar API

These models define the shape of data in API requests and responses.
Pydantic automatically validates data and converts types.

LEARNING NOTES:
- Pydantic models are like TypeScript interfaces but with runtime validation
- Field() lets you add descriptions, defaults, and constraints
- Use Optional[] for fields that might be None
- Nested models let you build complex data structures
"""

from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# PAPER MODELS
# =============================================================================

class PaperBase(BaseModel):
    """Base fields for a research paper."""
    title: str = Field(description="Paper title")
    authors: list[str] = Field(default=[], description="List of author names")
    abstract: str = Field(default="", description="Paper abstract")
    published_date: Optional[date] = Field(default=None, description="Publication date")
    url: str = Field(description="URL to paper page")
    pdf_url: Optional[str] = Field(default=None, description="Direct PDF link")


class PaperCreate(PaperBase):
    """Data needed to create a paper record."""
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    doi: Optional[str] = None
    source: str = Field(description="Where we found this paper")
    primary_category: str = Field(description="Primary topic category")
    relevance_score: float = Field(ge=0, le=1, description="Relevance to user interests")


class PaperResponse(PaperBase):
    """Paper data returned from API."""
    id: int
    arxiv_id: Optional[str] = None
    source: str
    primary_category: str
    relevance_score: float
    shown_date: date
    user_rating: Optional[int] = None
    bookmarked: bool = False
    
    class Config:
        from_attributes = True  # Allows conversion from SQLAlchemy models


class PaperSummary(BaseModel):
    """AI-generated paper summary."""
    paper: PaperResponse
    summary: str = Field(description="Plain language summary of the paper")
    key_findings: list[str] = Field(description="Main findings/contributions")
    relevance_explanation: str = Field(description="Why this paper is relevant to your interests")
    suggested_reading_time: int = Field(description="Estimated reading time in minutes")


# =============================================================================
# TOPIC & REVIEW MODELS
# =============================================================================

class TopicBase(BaseModel):
    """Base fields for a course topic."""
    id: str = Field(description="Unique topic identifier")
    name: str = Field(description="Topic name")
    course_id: str = Field(description="Course this topic belongs to")
    course_name: str = Field(description="Human-readable course name")


class TopicDetail(TopicBase):
    """Full topic details from configuration."""
    week_covered: int
    date_covered: Optional[date] = None
    key_concepts: list[str] = []
    learning_objectives: list[str] = []
    quiz_difficulty: str = "medium"
    prerequisites: list[str] = []


class TopicProgress(BaseModel):
    """User's progress on a topic."""
    topic_id: str
    times_reviewed: int = 0
    times_correct: int = 0
    average_score: float = 0.0
    streak: int = 0
    last_reviewed: Optional[datetime] = None
    next_review_date: Optional[date] = None
    mastery_level: str = Field(
        default="new",
        description="new, learning, reviewing, mastered"
    )


class TopicReview(BaseModel):
    """Generated topic review content."""
    topic: TopicDetail
    progress: Optional[TopicProgress] = None
    review_content: str = Field(description="AI-generated review material")
    key_points: list[str] = Field(description="Main points to remember")
    connections: list[str] = Field(description="Connections to other topics")
    practice_suggestions: list[str] = Field(description="Ways to practice this topic")


# =============================================================================
# QUIZ MODELS
# =============================================================================

class QuizQuestion(BaseModel):
    """A single quiz question."""
    id: str = Field(description="Unique question ID")
    topic_id: str
    course_id: str
    question_type: str = Field(
        description="Type: multiple_choice, true_false, short_answer, explain_concept, apply_scenario, compare_contrast"
    )
    question_text: str
    
    # For multiple choice
    options: Optional[list[str]] = Field(default=None, description="Answer options for MC questions")
    
    # The correct answer (hidden from initial response)
    correct_answer: str
    explanation: str = Field(description="Why this is the correct answer")
    
    # Metadata
    difficulty: str = Field(default="medium", description="easy, medium, hard")
    points: int = Field(default=1)


class QuizQuestionDisplay(BaseModel):
    """Question as shown to user (without answer)."""
    id: str
    topic_id: str
    topic_name: str
    course_name: str
    question_type: str
    question_text: str
    options: Optional[list[str]] = None
    difficulty: str
    points: int


class QuizAnswer(BaseModel):
    """User's answer to a question."""
    question_id: str
    user_answer: str
    time_taken_seconds: Optional[int] = None


class QuizResult(BaseModel):
    """Result of checking an answer."""
    question_id: str
    is_correct: bool
    score: float = Field(ge=0, le=1, description="0-1 score, allows partial credit")
    correct_answer: str
    explanation: str
    feedback: str = Field(description="Personalized feedback on the answer")


class QuizSession(BaseModel):
    """A complete quiz session."""
    id: str
    date: date
    questions: list[QuizQuestionDisplay]
    total_points: int


class QuizSessionResult(BaseModel):
    """Results of a completed quiz session."""
    session_id: str
    date: date
    results: list[QuizResult]
    total_score: float
    total_possible: int
    percentage: float
    topics_covered: list[str]
    areas_for_review: list[str] = Field(description="Topics that need more practice")


# =============================================================================
# DAILY CONTENT MODELS
# =============================================================================

class DailyContentResponse(BaseModel):
    """Complete daily learning content package."""
    date: date
    paper: PaperSummary
    topic_reviews: list[TopicReview]
    quiz: QuizSession
    supplementary_resources: list[dict] = Field(
        default=[],
        description="Additional resources related to today's topics"
    )
    estimated_time_minutes: int = Field(description="Total estimated completion time")
    
    # Progress info
    streak: int = Field(default=0, description="Consecutive days completed")
    weekly_progress: dict = Field(
        default={},
        description="Progress stats for the week"
    )


class DailyContentStatus(BaseModel):
    """Status of daily content for a given date."""
    date: date
    generated: bool
    completed: bool
    completed_at: Optional[datetime] = None
    paper_read: bool = False
    reviews_completed: bool = False
    quiz_completed: bool = False
    quiz_score: Optional[float] = None


# =============================================================================
# FILE UPLOAD MODELS
# =============================================================================

class FileUploadResponse(BaseModel):
    """Response after uploading a file."""
    id: int
    filename: str
    file_size_bytes: int
    mime_type: str
    course_id: Optional[str] = None
    topic_id: Optional[str] = None
    uploaded_at: datetime
    processing_status: str = Field(
        default="pending",
        description="pending, processing, completed, failed"
    )


class FileMetadataUpdate(BaseModel):
    """Update file metadata after upload."""
    course_id: Optional[str] = None
    topic_id: Optional[str] = None
    file_type: Optional[str] = None  # "lecture", "notes", "homework", "other"
    description: Optional[str] = None


# =============================================================================
# CONFIGURATION MODELS
# =============================================================================

class InterestConfig(BaseModel):
    """A single research interest."""
    name: str
    keywords: list[str]
    weight: float = 1.0
    arxiv_categories: list[str] = []


class CourseConfig(BaseModel):
    """Course configuration summary."""
    id: str
    name: str
    term: str
    topic_count: int
    topics_covered: int


class ConfigurationStatus(BaseModel):
    """Overall configuration status."""
    environment_valid: bool
    interests_valid: bool
    courses_valid: bool
    errors: list[str] = []
    interests_count: int = 0
    courses_count: int = 0
    topics_count: int = 0


# =============================================================================
# API RESPONSE WRAPPERS
# =============================================================================

class APIResponse(BaseModel):
    """Standard API response wrapper."""
    success: bool
    message: str = ""
    data: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None
