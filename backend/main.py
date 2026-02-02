"""
Daily Scholar - Main FastAPI Application

This is the entry point for the backend API. It:
1. Sets up the FastAPI application
2. Configures CORS for frontend access
3. Includes all API routers
4. Provides health check and config endpoints

LEARNING NOTES:
- FastAPI automatically generates OpenAPI docs at /docs
- CORS middleware allows the frontend to make requests
- Dependency injection provides database sessions
- Lifespan events handle startup/shutdown tasks

TO RUN:
    cd backend
    uvicorn main:app --reload

Then visit:
    http://localhost:8000/docs - Interactive API documentation
    http://localhost:8000/health - Health check
"""

from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings, validate_configuration, load_interests_config, load_courses_config
from .models import APIResponse, ConfigurationStatus, ErrorResponse


# =============================================================================
# APPLICATION LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handle application startup and shutdown.
    
    This runs before the app starts accepting requests and
    after it stops. Use it to:
    - Initialize database connections
    - Start background tasks
    - Clean up resources on shutdown
    """
    # STARTUP
    print("🚀 Starting Daily Scholar API...")
    
    # Validate configuration
    config_status = validate_configuration()
    if not config_status["environment"]["valid"]:
        print("⚠️  Environment configuration issues:")
        for error in config_status["environment"]["errors"]:
            print(f"   - {error}")
    
    if not config_status["interests"]["valid"]:
        print("⚠️  Interests configuration issues:")
        for error in config_status["interests"]["errors"]:
            print(f"   - {error}")
    
    if not config_status["courses"]["valid"]:
        print("⚠️  Courses configuration issues:")
        for error in config_status["courses"]["errors"]:
            print(f"   - {error}")
    
    print("✅ Daily Scholar API started!")
    
    yield  # Application runs here
    
    # SHUTDOWN
    print("👋 Shutting down Daily Scholar API...")


# =============================================================================
# APPLICATION SETUP
# =============================================================================

app = FastAPI(
    title="Daily Scholar API",
    description="""
    A personalized daily learning system for doctoral students.
    
    ## Features
    
    * **Paper Discovery** - Find relevant research papers daily
    * **Topic Reviews** - Study material for your courses
    * **Interactive Quizzes** - Test your knowledge with spaced repetition
    * **Progress Tracking** - Monitor your learning journey
    
    ## Getting Started
    
    1. Configure your interests in `config/interests.yaml`
    2. Add your courses in `config/courses.yaml`
    3. Set your API keys in `.env`
    4. Start learning!
    """,
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# CORE ENDPOINTS
# =============================================================================

@app.get("/", tags=["Core"])
async def root():
    """Root endpoint - basic API information."""
    return {
        "name": "Daily Scholar API",
        "version": "0.1.0",
        "status": "running",
        "docs_url": "/docs",
        "health_url": "/health",
    }


@app.get("/health", tags=["Core"])
async def health_check():
    """
    Health check endpoint.
    
    Use this to verify the API is running and configured correctly.
    """
    config_status = validate_configuration()
    
    all_valid = all([
        config_status["environment"]["valid"],
        config_status["interests"]["valid"],
        config_status["courses"]["valid"],
    ])
    
    return {
        "status": "healthy" if all_valid else "degraded",
        "timestamp": date.today().isoformat(),
        "configuration": {
            "environment": "✓" if config_status["environment"]["valid"] else "✗",
            "interests": "✓" if config_status["interests"]["valid"] else "✗",
            "courses": "✓" if config_status["courses"]["valid"] else "✗",
        }
    }


@app.get("/config/status", response_model=ConfigurationStatus, tags=["Configuration"])
async def get_configuration_status():
    """
    Get detailed configuration status.
    
    Returns information about:
    - Environment variable validity
    - Interests configuration
    - Courses configuration
    """
    status = validate_configuration()
    
    # Count interests and courses
    interests_count = 0
    courses_count = 0
    topics_count = 0
    
    try:
        interests_config = load_interests_config()
        for category in ["primary", "secondary", "exploratory"]:
            interests_count += len(interests_config.get("interests", {}).get(category, []))
    except Exception:
        pass
    
    try:
        courses_config = load_courses_config()
        for course in courses_config.get("courses", []):
            courses_count += 1
            topics_count += len(course.get("topics", []))
    except Exception:
        pass
    
    # Collect all errors
    errors = []
    for section in ["environment", "interests", "courses"]:
        errors.extend(status[section]["errors"])
    
    return ConfigurationStatus(
        environment_valid=status["environment"]["valid"],
        interests_valid=status["interests"]["valid"],
        courses_valid=status["courses"]["valid"],
        errors=errors,
        interests_count=interests_count,
        courses_count=courses_count,
        topics_count=topics_count,
    )


@app.get("/config/interests", tags=["Configuration"])
async def get_interests():
    """Get the current interests configuration."""
    try:
        return load_interests_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/config/courses", tags=["Configuration"])
async def get_courses():
    """Get the current courses configuration."""
    try:
        return load_courses_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# PAPER ENDPOINTS
# =============================================================================

@app.get("/papers/discover", tags=["Papers"])
async def discover_papers(
    max_results: int = 10,
    days_back: int = 30,
):
    """
    Discover relevant papers based on your interests.
    
    This searches arXiv and Semantic Scholar for papers matching
    your configured interests.
    
    Args:
        max_results: Maximum number of papers to return
        days_back: Only search papers from the last N days
    """
    from .services import PaperDiscoveryService
    
    service = PaperDiscoveryService()
    try:
        papers = await service.discover_papers(
            max_results=max_results,
            days_back=days_back,
        )
        return {
            "count": len(papers),
            "papers": [p.to_dict() for p in papers],
        }
    finally:
        await service.close()


@app.get("/papers/daily", tags=["Papers"])
async def get_daily_paper():
    """
    Get today's recommended paper.
    
    Returns a single paper selected for today's learning,
    along with an AI-generated summary.
    """
    from .services import PaperDiscoveryService, ContentGeneratorService
    
    discovery = PaperDiscoveryService()
    generator = ContentGeneratorService()
    
    try:
        # Get the best paper (in production, we'd check against seen papers in DB)
        paper = await discovery.select_daily_paper(seen_ids=[], days_back=14)
        
        if not paper:
            return {"message": "No suitable papers found today", "paper": None}
        
        # Generate summary
        summary = await generator.generate_paper_summary(paper)
        
        return {
            "paper": paper.to_dict(),
            "summary": summary,
        }
    finally:
        await discovery.close()


# =============================================================================
# TOPIC ENDPOINTS
# =============================================================================

@app.get("/topics", tags=["Topics"])
async def get_all_topics():
    """Get all topics from all courses."""
    from .config import get_all_topics
    return {"topics": get_all_topics()}


@app.get("/topics/{topic_id}/review", tags=["Topics"])
async def get_topic_review(topic_id: str):
    """
    Get an AI-generated review for a specific topic.
    
    Args:
        topic_id: The unique ID of the topic to review
    """
    from .config import get_all_topics, load_courses_config
    from .services import ContentGeneratorService
    
    # Find the topic
    all_topics = get_all_topics()
    topic = next((t for t in all_topics if t["id"] == topic_id), None)
    
    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    
    # Find the course
    courses_config = load_courses_config()
    course = next(
        (c for c in courses_config.get("courses", []) if c["id"] == topic["course_id"]),
        None
    )
    
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    
    # Generate review
    generator = ContentGeneratorService()
    review = await generator.generate_topic_review(topic, course)
    
    return {
        "topic": topic,
        "review": review,
    }


# =============================================================================
# QUIZ ENDPOINTS
# =============================================================================

@app.get("/quiz/generate/{topic_id}", tags=["Quiz"])
async def generate_quiz(
    topic_id: str,
    count: int = 5,
    difficulty: str = "medium",
):
    """
    Generate a quiz for a specific topic.
    
    Args:
        topic_id: The topic to quiz on
        count: Number of questions
        difficulty: easy, medium, or hard
    """
    from .config import get_all_topics, load_courses_config
    from .services import ContentGeneratorService
    
    # Find topic and course
    all_topics = get_all_topics()
    topic = next((t for t in all_topics if t["id"] == topic_id), None)
    
    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    
    courses_config = load_courses_config()
    course = next(
        (c for c in courses_config.get("courses", []) if c["id"] == topic["course_id"]),
        None
    )
    
    # Generate questions
    generator = ContentGeneratorService()
    questions = await generator.generate_quiz_questions(
        topic, course, count=count, difficulty=difficulty
    )
    
    # Return questions without answers (for the quiz UI)
    questions_for_display = []
    for q in questions:
        display_q = {
            "id": q["id"],
            "topic_id": q["topic_id"],
            "topic_name": topic["name"],
            "course_name": course["name"],
            "question_type": q["question_type"],
            "question_text": q["question_text"],
            "options": q.get("options"),
            "difficulty": q["difficulty"],
            "points": q["points"],
        }
        questions_for_display.append(display_q)
    
    # Store full questions in memory for answer checking
    # In production, store in database or session
    app.state.current_questions = {q["id"]: q for q in questions}
    
    return {
        "topic": topic["name"],
        "course": course["name"],
        "questions": questions_for_display,
        "total_points": sum(q["points"] for q in questions),
    }


@app.post("/quiz/answer", tags=["Quiz"])
async def check_answer(question_id: str, answer: str):
    """
    Check an answer to a quiz question.
    
    Args:
        question_id: ID of the question being answered
        answer: The user's answer
    """
    from .services import ContentGeneratorService
    
    # Get the question
    questions = getattr(app.state, "current_questions", {})
    question = questions.get(question_id)
    
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    
    # Evaluate answer
    generator = ContentGeneratorService()
    result = await generator.evaluate_answer(question, answer)
    
    return result


# =============================================================================
# DAILY CONTENT ENDPOINT
# =============================================================================

@app.get("/daily", tags=["Daily"])
async def get_daily_content():
    """
    Get today's complete learning package.
    
    Includes:
    - Today's paper with summary
    - Topic reviews (one from each course)
    - Quiz questions
    - Supplementary resources
    
    This is the main endpoint for the daily learning flow.
    """
    from .config import get_all_topics, load_courses_config
    from .services import PaperDiscoveryService, ContentGeneratorService
    
    discovery = PaperDiscoveryService()
    generator = ContentGeneratorService()
    
    try:
        # 1. Get today's paper
        paper = await discovery.select_daily_paper(seen_ids=[], days_back=14)
        paper_summary = None
        if paper:
            paper_summary = await generator.generate_paper_summary(paper)
        
        # 2. Select topics for review (one from each course)
        courses_config = load_courses_config()
        all_topics = get_all_topics()
        
        topic_reviews = []
        quiz_questions = []
        
        for course in courses_config.get("courses", []):
            course_topics = [t for t in all_topics if t["course_id"] == course["id"]]
            
            if course_topics:
                # Select first topic (in production, use spaced repetition)
                topic = course_topics[0]
                
                # Generate review
                review = await generator.generate_topic_review(topic, course)
                topic_reviews.append({
                    "topic": topic,
                    "review": review,
                })
                
                # Generate quiz questions
                questions = await generator.generate_quiz_questions(
                    topic, course, count=2, difficulty="medium"
                )
                quiz_questions.extend(questions)
        
        # 3. Get supplementary resources
        topics_for_resources = [tr["topic"] for tr in topic_reviews]
        resources = await generator.suggest_resources(topics_for_resources, paper)
        
        # Store questions for answer checking
        app.state.current_questions = {q["id"]: q for q in quiz_questions}
        
        # Hide answers from response
        questions_display = []
        for q in quiz_questions:
            questions_display.append({
                "id": q["id"],
                "topic_id": q["topic_id"],
                "question_type": q["question_type"],
                "question_text": q["question_text"],
                "options": q.get("options"),
                "difficulty": q["difficulty"],
                "points": q["points"],
            })
        
        return {
            "date": date.today().isoformat(),
            "paper": paper.to_dict() if paper else None,
            "paper_summary": paper_summary,
            "topic_reviews": topic_reviews,
            "quiz": {
                "questions": questions_display,
                "total_points": sum(q["points"] for q in quiz_questions),
            },
            "resources": resources,
            "estimated_time_minutes": 45,  # Rough estimate
        }
        
    finally:
        await discovery.close()


# =============================================================================
# INCLUDE ROUTERS (for future expansion)
# =============================================================================

# TODO: Add routers for more complex functionality
# from .routers import papers, topics, quiz, upload
# app.include_router(papers.router, prefix="/papers", tags=["Papers"])
# app.include_router(topics.router, prefix="/topics", tags=["Topics"])
# app.include_router(quiz.router, prefix="/quiz", tags=["Quiz"])
# app.include_router(upload.router, prefix="/upload", tags=["Upload"])
