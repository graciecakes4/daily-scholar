"""
Daily Scholar - Main FastAPI Application

TO RUN:
    cd ~/daily-scholar
    uvicorn backend.main:app --reload

Then visit:
    http://localhost:8000/docs - Interactive API documentation
    http://localhost:8000/health - Health check
"""

from contextlib import asynccontextmanager
from datetime import datetime, date
import random
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List

from .config import get_settings, validate_configuration, load_interests_config, load_courses_config
from .models import ConfigurationStatus
from .database import (
    create_tables, get_session,
    ArchivedPaper, ArchivedTopicReview, ArchivedQuiz
)


# =============================================================================
# PYDANTIC MODELS FOR ARCHIVE ENDPOINTS
# =============================================================================

class ArchivePaperRequest(BaseModel):
    title: str
    authors: List[str]
    abstract: Optional[str] = None
    url: str
    pdf_url: Optional[str] = None
    source: str
    primary_category: Optional[str] = None
    relevance_score: Optional[float] = None
    published_date: Optional[str] = None
    arxiv_id: Optional[str] = None
    summary: Optional[str] = None
    key_findings: Optional[List[str]] = None
    user_notes: Optional[str] = None
    user_rating: Optional[int] = None


class ArchiveTopicRequest(BaseModel):
    topic_id: str
    topic_name: str
    course_id: str
    course_name: str
    week_covered: Optional[int] = None
    review_content: str
    key_points: List[str]
    connections: List[str]
    practice_suggestions: List[str]
    key_concepts: Optional[List[str]] = None
    user_notes: Optional[str] = None
    confidence_level: Optional[int] = None


class ArchiveQuizRequest(BaseModel):
    topics: List[str]
    total_questions: int
    total_points: int
    score_earned: float
    percentage: float
    questions: List[dict]
    duration_seconds: Optional[int] = None


class UpdatePaperRequest(BaseModel):
    user_notes: Optional[str] = None
    user_rating: Optional[int] = None
    read_status: Optional[str] = None


class UpdateTopicRequest(BaseModel):
    user_notes: Optional[str] = None
    confidence_level: Optional[int] = None


# =============================================================================
# APPLICATION LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Daily Scholar API...")
    create_tables()
    config_status = validate_configuration()
    if not config_status["environment"]["valid"]:
        print("⚠️  Environment configuration issues")
    print("✅ Daily Scholar API started!")
    yield
    print("👋 Shutting down Daily Scholar API...")


# =============================================================================
# APPLICATION SETUP
# =============================================================================

app = FastAPI(
    title="Daily Scholar API",
    description="A personalized daily learning system for doctoral students.",
    version="0.2.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# CORE ENDPOINTS
# =============================================================================

@app.get("/", tags=["Core"])
async def root():
    return {"name": "Daily Scholar API", "version": "0.2.0", "status": "running"}


@app.get("/health", tags=["Core"])
async def health_check():
    config_status = validate_configuration()
    all_valid = all([config_status["environment"]["valid"], config_status["interests"]["valid"], config_status["courses"]["valid"]])
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
    status = validate_configuration()
    interests_count = courses_count = topics_count = 0
    try:
        interests_config = load_interests_config()
        for category in ["primary", "secondary", "exploratory"]:
            interests_count += len(interests_config.get("interests", {}).get(category, []))
    except: pass
    try:
        courses_config = load_courses_config()
        for course in courses_config.get("courses", []):
            courses_count += 1
            topics_count += len(course.get("topics", []))
    except: pass
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
    try:
        return load_interests_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/config/courses", tags=["Configuration"])
async def get_courses():
    try:
        return load_courses_config()
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =============================================================================
# ARCHIVE ENDPOINTS - PAPERS
# =============================================================================

@app.post("/archive/papers", tags=["Archive"])
async def archive_paper(request: ArchivePaperRequest):
    session = get_session()
    try:
        paper = ArchivedPaper(
            title=request.title,
            authors=json.dumps(request.authors),
            abstract=request.abstract,
            url=request.url,
            pdf_url=request.pdf_url,
            source=request.source,
            primary_category=request.primary_category,
            relevance_score=request.relevance_score,
            published_date=request.published_date,
            arxiv_id=request.arxiv_id,
            summary=request.summary,
            key_findings=request.key_findings,
            user_notes=request.user_notes,
            user_rating=request.user_rating,
            read_status="completed" if request.user_rating else "reading",
        )
        session.add(paper)
        session.commit()
        session.refresh(paper)
        return {"message": "Paper archived successfully", "id": paper.id}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/archive/papers", tags=["Archive"])
async def get_archived_papers(limit: int = 50, offset: int = 0, status: Optional[str] = None):
    session = get_session()
    try:
        query = session.query(ArchivedPaper).order_by(ArchivedPaper.archived_at.desc())
        if status:
            query = query.filter(ArchivedPaper.read_status == status)
        papers = query.offset(offset).limit(limit).all()
        total = query.count()
        return {
            "papers": [{
                "id": p.id, "title": p.title,
                "authors": json.loads(p.authors) if p.authors else [],
                "abstract": p.abstract, "url": p.url, "pdf_url": p.pdf_url,
                "source": p.source, "primary_category": p.primary_category,
                "summary": p.summary, "key_findings": p.key_findings,
                "user_notes": p.user_notes, "user_rating": p.user_rating,
                "read_status": p.read_status,
                "archived_at": p.archived_at.isoformat() if p.archived_at else None,
            } for p in papers],
            "total": total, "limit": limit, "offset": offset,
        }
    finally:
        session.close()


@app.put("/archive/papers/{paper_id}", tags=["Archive"])
async def update_archived_paper(paper_id: int, request: UpdatePaperRequest):
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(ArchivedPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        if request.user_notes is not None:
            paper.user_notes = request.user_notes
        if request.user_rating is not None:
            paper.user_rating = request.user_rating
        if request.read_status is not None:
            paper.read_status = request.read_status
            if request.read_status == "completed":
                paper.completed_at = datetime.utcnow()
        session.commit()
        return {"message": "Paper updated successfully"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.delete("/archive/papers/{paper_id}", tags=["Archive"])
async def delete_archived_paper(paper_id: int):
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(ArchivedPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        session.delete(paper)
        session.commit()
        return {"message": "Paper deleted successfully"}
    finally:
        session.close()


# =============================================================================
# ARCHIVE ENDPOINTS - TOPICS
# =============================================================================

@app.post("/archive/topics", tags=["Archive"])
async def archive_topic_review(request: ArchiveTopicRequest):
    session = get_session()
    try:
        existing = session.query(ArchivedTopicReview).filter(ArchivedTopicReview.topic_id == request.topic_id).first()
        if existing:
            existing.review_content = request.review_content
            existing.key_points = request.key_points
            existing.connections = request.connections
            existing.practice_suggestions = request.practice_suggestions
            existing.review_count += 1
            existing.last_reviewed_at = datetime.utcnow()
            if request.user_notes:
                existing.user_notes = request.user_notes
            if request.confidence_level:
                existing.confidence_level = request.confidence_level
            session.commit()
            return {"message": "Topic review updated", "id": existing.id, "review_count": existing.review_count}
        
        topic = ArchivedTopicReview(
            topic_id=request.topic_id, topic_name=request.topic_name,
            course_id=request.course_id, course_name=request.course_name,
            week_covered=request.week_covered, review_content=request.review_content,
            key_points=request.key_points, connections=request.connections,
            practice_suggestions=request.practice_suggestions, key_concepts=request.key_concepts,
            user_notes=request.user_notes, confidence_level=request.confidence_level,
        )
        session.add(topic)
        session.commit()
        session.refresh(topic)
        return {"message": "Topic review archived successfully", "id": topic.id}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/archive/topics", tags=["Archive"])
async def get_archived_topics(limit: int = 50, offset: int = 0, course_id: Optional[str] = None):
    session = get_session()
    try:
        query = session.query(ArchivedTopicReview).order_by(ArchivedTopicReview.last_reviewed_at.desc())
        if course_id:
            query = query.filter(ArchivedTopicReview.course_id == course_id)
        topics = query.offset(offset).limit(limit).all()
        total = query.count()
        return {
            "topics": [{
                "id": t.id, "topic_id": t.topic_id, "topic_name": t.topic_name,
                "course_id": t.course_id, "course_name": t.course_name,
                "week_covered": t.week_covered, "review_content": t.review_content,
                "key_points": t.key_points, "connections": t.connections,
                "practice_suggestions": t.practice_suggestions, "key_concepts": t.key_concepts,
                "user_notes": t.user_notes, "confidence_level": t.confidence_level,
                "review_count": t.review_count,
                "first_reviewed_at": t.first_reviewed_at.isoformat() if t.first_reviewed_at else None,
                "last_reviewed_at": t.last_reviewed_at.isoformat() if t.last_reviewed_at else None,
            } for t in topics],
            "total": total, "limit": limit, "offset": offset,
        }
    finally:
        session.close()


@app.put("/archive/topics/{topic_db_id}", tags=["Archive"])
async def update_archived_topic(topic_db_id: int, request: UpdateTopicRequest):
    session = get_session()
    try:
        topic = session.query(ArchivedTopicReview).filter(ArchivedTopicReview.id == topic_db_id).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic review not found")
        if request.user_notes is not None:
            topic.user_notes = request.user_notes
        if request.confidence_level is not None:
            topic.confidence_level = request.confidence_level
        session.commit()
        return {"message": "Topic updated successfully"}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.delete("/archive/topics/{topic_db_id}", tags=["Archive"])
async def delete_archived_topic(topic_db_id: int):
    session = get_session()
    try:
        topic = session.query(ArchivedTopicReview).filter(ArchivedTopicReview.id == topic_db_id).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic review not found")
        session.delete(topic)
        session.commit()
        return {"message": "Topic deleted successfully"}
    finally:
        session.close()


# =============================================================================
# ARCHIVE ENDPOINTS - QUIZZES
# =============================================================================

@app.post("/archive/quizzes", tags=["Archive"])
async def archive_quiz(request: ArchiveQuizRequest):
    session = get_session()
    try:
        quiz = ArchivedQuiz(
            topics=request.topics, total_questions=request.total_questions,
            total_points=request.total_points, score_earned=request.score_earned,
            percentage=request.percentage, questions=request.questions,
            duration_seconds=request.duration_seconds,
        )
        session.add(quiz)
        session.commit()
        session.refresh(quiz)
        return {"message": "Quiz archived successfully", "id": quiz.id}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/archive/quizzes", tags=["Archive"])
async def get_archived_quizzes(limit: int = 50, offset: int = 0):
    session = get_session()
    try:
        query = session.query(ArchivedQuiz).order_by(ArchivedQuiz.taken_at.desc())
        quizzes = query.offset(offset).limit(limit).all()
        total = query.count()
        return {
            "quizzes": [{
                "id": q.id, "topics": q.topics, "total_questions": q.total_questions,
                "total_points": q.total_points, "score_earned": q.score_earned,
                "percentage": q.percentage, "questions": q.questions,
                "duration_seconds": q.duration_seconds,
                "taken_at": q.taken_at.isoformat() if q.taken_at else None,
            } for q in quizzes],
            "total": total, "limit": limit, "offset": offset,
        }
    finally:
        session.close()


@app.delete("/archive/quizzes/{quiz_id}", tags=["Archive"])
async def delete_archived_quiz(quiz_id: int):
    session = get_session()
    try:
        quiz = session.query(ArchivedQuiz).filter(ArchivedQuiz.id == quiz_id).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        session.delete(quiz)
        session.commit()
        return {"message": "Quiz deleted successfully"}
    finally:
        session.close()


# =============================================================================
# ARCHIVE STATS
# =============================================================================

@app.get("/archive/stats", tags=["Archive"])
async def get_archive_stats():
    session = get_session()
    try:
        papers_count = session.query(ArchivedPaper).count()
        papers_completed = session.query(ArchivedPaper).filter(ArchivedPaper.read_status == "completed").count()
        topics_count = session.query(ArchivedTopicReview).count()
        total_reviews = sum(r[0] for r in session.query(ArchivedTopicReview.review_count).all()) or 0
        quizzes_count = session.query(ArchivedQuiz).count()
        quiz_scores = [s[0] for s in session.query(ArchivedQuiz.percentage).all()]
        avg_quiz_score = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0
        return {
            "papers": {"total": papers_count, "completed": papers_completed},
            "topics": {"unique_topics": topics_count, "total_reviews": total_reviews},
            "quizzes": {"total": quizzes_count, "average_score": round(avg_quiz_score, 1)},
        }
    finally:
        session.close()


# =============================================================================
# PAPER ENDPOINTS
# =============================================================================

@app.get("/papers/discover", tags=["Papers"])
async def discover_papers(max_results: int = 10, days_back: int = 30):
    from .services import PaperDiscoveryService
    service = PaperDiscoveryService()
    try:
        papers = await service.discover_papers(max_results=max_results, days_back=days_back)
        return {"count": len(papers), "papers": [p.to_dict() for p in papers]}
    finally:
        await service.close()


@app.get("/papers/daily", tags=["Papers"])
async def get_daily_paper():
    from .services import PaperDiscoveryService, ContentGeneratorService
    discovery = PaperDiscoveryService()
    generator = ContentGeneratorService()
    try:
        paper = await discovery.select_daily_paper(seen_ids=[], days_back=14)
        if not paper:
            return {"message": "No suitable papers found today", "paper": None}
        summary = await generator.generate_paper_summary(paper)
        return {"paper": paper.to_dict(), "summary": summary}
    finally:
        await discovery.close()
        await generator.close()


# =============================================================================
# TOPIC ENDPOINTS
# =============================================================================

@app.get("/topics", tags=["Topics"])
async def get_all_topics():
    from .config import get_all_topics
    return {"topics": get_all_topics()}


@app.get("/topics/{topic_id}/review", tags=["Topics"])
async def get_topic_review(topic_id: str):
    from .config import get_all_topics, load_courses_config
    from .services import ContentGeneratorService
    all_topics = get_all_topics()
    topic = next((t for t in all_topics if t["id"] == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    courses_config = load_courses_config()
    course = next((c for c in courses_config.get("courses", []) if c["id"] == topic["course_id"]), None)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    generator = ContentGeneratorService()
    try:
        review = await generator.generate_topic_review(topic, course)
        return {"topic": topic, "review": review}
    finally:
        await generator.close()


# =============================================================================
# QUIZ ENDPOINTS
# =============================================================================

@app.get("/quiz/generate/{topic_id}", tags=["Quiz"])
async def generate_quiz(topic_id: str, count: int = 5, difficulty: str = "medium"):
    from .config import get_all_topics, load_courses_config
    from .services import ContentGeneratorService
    all_topics = get_all_topics()
    topic = next((t for t in all_topics if t["id"] == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
    courses_config = load_courses_config()
    course = next((c for c in courses_config.get("courses", []) if c["id"] == topic["course_id"]), None)
    generator = ContentGeneratorService()
    try:
        questions = await generator.generate_quiz_questions(topic, course, count=count, difficulty=difficulty)
        questions_for_display = [{
            "id": q["id"], "topic_id": q["topic_id"], "topic_name": topic["name"],
            "course_name": course["name"], "question_type": q["question_type"],
            "question_text": q["question_text"], "options": q.get("options"),
            "difficulty": q["difficulty"], "points": q["points"],
        } for q in questions]
        app.state.current_questions = {q["id"]: q for q in questions}
        return {"topic": topic["name"], "course": course["name"], "questions": questions_for_display, "total_points": sum(q["points"] for q in questions)}
    finally:
        await generator.close()


@app.post("/quiz/regenerate", tags=["Quiz"])
async def regenerate_quiz(count: int = 5, difficulty: str = "medium"):
    from .config import get_all_topics, load_courses_config
    from .services import ContentGeneratorService
    all_topics = get_all_topics()
    courses_config = load_courses_config()
    if not all_topics:
        raise HTTPException(status_code=404, detail="No topics configured")
    courses = courses_config.get("courses", [])
    selected_topics = []
    for course in courses:
        course_topics = [t for t in all_topics if t["course_id"] == course["id"]]
        if course_topics:
            selected_topics.append(random.choice(course_topics))
    if not selected_topics:
        selected_topics = random.sample(all_topics, min(2, len(all_topics)))
    generator = ContentGeneratorService()
    try:
        all_questions = []
        questions_per_topic = max(1, count // len(selected_topics))
        for topic in selected_topics:
            course = next((c for c in courses if c["id"] == topic["course_id"]), {"id": "unknown", "name": "Unknown Course"})
            questions = await generator.generate_quiz_questions(topic, course, count=questions_per_topic, difficulty=difficulty)
            for q in questions:
                q["topic_name"] = topic["name"]
                q["course_name"] = course["name"]
            all_questions.extend(questions)
        random.shuffle(all_questions)
        all_questions = all_questions[:count]
        app.state.current_questions = {q["id"]: q for q in all_questions}
        questions_display = [{
            "id": q["id"], "topic_id": q["topic_id"], "topic_name": q.get("topic_name", ""),
            "course_name": q.get("course_name", ""), "question_type": q["question_type"],
            "question_text": q["question_text"], "options": q.get("options"),
            "difficulty": q["difficulty"], "points": q["points"],
        } for q in all_questions]
        return {"topics": [t["name"] for t in selected_topics], "questions": questions_display, "total_points": sum(q["points"] for q in all_questions)}
    finally:
        await generator.close()


@app.post("/quiz/answer", tags=["Quiz"])
async def check_answer(question_id: str, answer: str):
    from .services import ContentGeneratorService
    questions = getattr(app.state, "current_questions", {})
    question = questions.get(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    generator = ContentGeneratorService()
    try:
        result = await generator.evaluate_answer(question, answer)
        return result
    finally:
        await generator.close()


# =============================================================================
# DAILY CONTENT ENDPOINT
# =============================================================================

@app.get("/daily", tags=["Daily"])
async def get_daily_content():
    from .config import get_all_topics, load_courses_config
    from .services import PaperDiscoveryService, ContentGeneratorService
    discovery = PaperDiscoveryService()
    generator = ContentGeneratorService()
    try:
        paper = await discovery.select_daily_paper(seen_ids=[], days_back=14)
        paper_summary = None
        if paper:
            paper_summary = await generator.generate_paper_summary(paper)
        courses_config = load_courses_config()
        all_topics = get_all_topics()
        topic_reviews = []
        quiz_questions = []
        for course in courses_config.get("courses", []):
            course_topics = [t for t in all_topics if t["course_id"] == course["id"]]
            if course_topics:
                topic = course_topics[0]
                review = await generator.generate_topic_review(topic, course)
                topic_reviews.append({"topic": topic, "review": review})
                questions = await generator.generate_quiz_questions(topic, course, count=2, difficulty="medium")
                quiz_questions.extend(questions)
        topics_for_resources = [tr["topic"] for tr in topic_reviews]
        resources = await generator.suggest_resources(topics_for_resources, paper)
        app.state.current_questions = {q["id"]: q for q in quiz_questions}
        questions_display = [{
            "id": q["id"], "topic_id": q["topic_id"], "question_type": q["question_type"],
            "question_text": q["question_text"], "options": q.get("options"),
            "difficulty": q["difficulty"], "points": q["points"],
        } for q in quiz_questions]
        return {
            "date": date.today().isoformat(),
            "paper": paper.to_dict() if paper else None,
            "paper_summary": paper_summary,
            "topic_reviews": topic_reviews,
            "quiz": {"questions": questions_display, "total_points": sum(q["points"] for q in quiz_questions)},
            "resources": resources,
            "estimated_time_minutes": 45,
        }
    finally:
        await discovery.close()
        await generator.close()
