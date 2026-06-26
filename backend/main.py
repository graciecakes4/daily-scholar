"""
Daily Scholar - Main FastAPI Application

Full paper lifecycle with:
- Automatic seen paper tracking
- PDF upload/download
- Archive management
- User stats
- Topic rotation with completion tracking
"""

from contextlib import asynccontextmanager
from datetime import datetime, date
from pathlib import Path
import random
import json
import shutil
import uuid
import httpx

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List

from .auth import get_current_user_id
from .config import get_settings, validate_configuration
from .models import ConfigurationStatus
from .database import (
    create_tables, get_session, get_seen_paper_ids, mark_paper_as_seen, update_user_streak,
    get_completed_topic_ids, get_review_later_topic_ids, get_recently_reviewed_topic_ids,
    get_or_create_user_stats,
    SeenPaper, ArchivedPaper, ArchivedTopicReview, ArchivedQuiz, PaperPDF, UserStats, DailyContentCache
)


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class ArchivePaperRequest(BaseModel):
    # From paper discovery
    unique_id: Optional[str] = None
    title: str
    authors: List[str]
    abstract: Optional[str] = None
    url: str
    pdf_url: Optional[str] = None
    source: str
    primary_category: Optional[str] = None
    categories: Optional[List[str]] = None
    relevance_score: Optional[float] = None
    published_date: Optional[str] = None
    arxiv_id: Optional[str] = None
    semantic_scholar_id: Optional[str] = None
    doi: Optional[str] = None
    # AI summary
    summary: Optional[str] = None
    key_findings: Optional[List[str]] = None
    # User input
    user_notes: Optional[str] = None
    user_rating: Optional[int] = None
    read_status: Optional[str] = "unread"
    linked_topic_ids: Optional[List[str]] = None


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
    linked_paper_ids: Optional[List[int]] = None
    status: Optional[str] = "active"


class ArchiveQuizRequest(BaseModel):
    topics: List[str]
    topic_ids: Optional[List[str]] = None
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
    linked_topic_ids: Optional[List[str]] = None


class UpdateTopicRequest(BaseModel):
    user_notes: Optional[str] = None
    confidence_level: Optional[int] = None
    linked_paper_ids: Optional[List[int]] = None
    status: Optional[str] = None


class TopicStatusRequest(BaseModel):
    status: str  # "active", "completed", "review_later"


# =============================================================================
# APPLICATION LIFESPAN
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting Daily Scholar API...")
    create_tables()
    # bootstrap topics from config/topics/*.yaml (DB-wins; insert-only)
    from .services.topic_loader import bootstrap_topics_from_yaml
    summary = bootstrap_topics_from_yaml()
    print(
        f"  ↳ Topics bootstrapped: "
        f"{summary['inserted']} inserted, "
        f"{summary['preserved']} preserved, "
        f"{summary['marked_orphaned']} marked orphaned"
    )
    # APScheduler nightly daily-content job
    from .services.scheduler import start_scheduler, stop_scheduler
    sched = start_scheduler()
    if sched is not None:
        print(f"  ↳ Scheduler started with {len(sched.get_jobs())} job(s)")
    print("✅ Daily Scholar API started!")
    yield
    print("👋 Shutting down Daily Scholar API...")
    stop_scheduler()


# =============================================================================
# APPLICATION SETUP
# =============================================================================

app = FastAPI(
    title="Daily Scholar API",
    description="A personalized daily learning system with full paper lifecycle management.",
    version="0.4.0",
    lifespan=lifespan,
)

settings = get_settings()


def _resolve_cors_origins() -> list[str]:
    """
    Build the CORS allowlist from settings.

    Precedence:
      1. CORS_ALLOWED_ORIGINS (comma-separated) — explicit override; wins outright.
      2. FRONTEND_URL + the two localhost variants — back-compat default.

    Origins are stripped of surrounding whitespace and trailing slashes so
    `credentials: 'include'` matches byte-for-byte. Empty entries dropped.
    """
    if settings.cors_allowed_origins:
        raw = settings.cors_allowed_origins.split(",")
    else:
        raw = [settings.frontend_url, "http://localhost:3000", "http://127.0.0.1:3000"]
    seen: set[str] = set()
    origins: list[str] = []
    for o in raw:
        o = o.strip().rstrip("/")
        if o and o not in seen:
            seen.add(o)
            origins.append(o)
    return origins


app.add_middleware(
    CORSMiddleware,
    allow_origins=_resolve_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Beta hardening middleware: rate limit + CSRF.
#
# Rate limiting is custom (backend/middleware/rate_limit.py) rather than
# slowapi because slowapi's decorator approach broke FastAPI's body
# introspection. The middleware sits in front of all routes and matches
# on (method, path) per DEFAULT_POLICIES.
#
# CSRF uses the double-submit-cookie pattern. Both middlewares no-op
# when their respective env flags are set (RATE_LIMIT_DISABLED=1 /
# CSRF_DISABLED=1) — defaults in conftest for tests.
# ---------------------------------------------------------------------------

from .middleware.csrf import CSRFMiddleware
from .middleware.rate_limit import RateLimitMiddleware

app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)

# topics_router and scope_router are mounted at the END of main.py so the
# specific @app.get paths (/topics/status-summary, /topics/random-review,
# /topics/{id}/review) take precedence over the router's catch-all /topics/{id}.


# =============================================================================
# TOPIC SELECTION + ADAPTER HELPERS (moved to services/daily_content.py;
# re-exported here so other endpoints in main.py can keep importing them
# from the old location)
# =============================================================================

from .services.daily_content import (
    _PaperLite,
    _select_topic_from_scope,
    _stream_display_name,
    _topic_pseudo_course,
    _topic_to_dict,
)


def _get_topic_or_404(topic_id: str):
    """Load a Topic row from the DB or raise 404."""
    from .database import Topic as TopicModel
    session = get_session()
    try:
        topic = session.get(TopicModel, topic_id)
        if topic is None:
            raise HTTPException(status_code=404, detail=f"Topic '{topic_id}' not found")
        # detach so callers can use it after the session closes
        session.expunge(topic)
        return topic
    finally:
        session.close()


# =============================================================================
# CORE ENDPOINTS
# =============================================================================

@app.get("/", tags=["Core"])
async def root():
    return {"name": "Daily Scholar API", "version": "0.4.0", "status": "running"}


@app.get("/health", tags=["Core"])
async def health_check():
    """
    TRULY lightweight health check — for load balancer / Railway probes.

    Returns 200 the moment uvicorn can serve, with zero DB / external deps.
    This is what Railway, Cloudflare, and uptime monitors should hit.

    For per-subsystem health (DB, LLM providers, storage, push), use /health/deep.
    """
    return {
        "status": "ok",
        "timestamp": date.today().isoformat(),
    }


@app.get("/config/status", response_model=ConfigurationStatus, tags=["Configuration"])
async def get_configuration_status():
    """
    Report on the topic-table state plus environment validity. The legacy
    interests/courses YAMLs are no longer consulted; counts come from the DB.
    """
    from .database import Topic as TopicModel

    status = validate_configuration()
    session = get_session()
    try:
        topics_count = session.query(TopicModel).count()
        active_count = session.query(TopicModel).filter(TopicModel.active.is_(True)).count()
        streams_count = session.query(TopicModel.stream).distinct().count()
    finally:
        session.close()

    errors = list(status["environment"]["errors"])

    return ConfigurationStatus(
        environment_valid=status["environment"]["valid"],
        # 'interests_valid' / 'courses_valid' now reflect the unified topic
        # store: valid if at least one active topic exists.
        interests_valid=active_count > 0,
        courses_valid=streams_count > 0,
        errors=errors,
        interests_count=active_count,
        courses_count=streams_count,
        topics_count=topics_count,
    )


# =============================================================================
# USER STATS
# =============================================================================

@app.get("/stats", tags=["Stats"])
async def get_user_stats(user_id: str = Depends(get_current_user_id)):
    """Get comprehensive user learning statistics."""
    session = get_session()
    try:
        stats = session.query(UserStats).filter(UserStats.user_id == user_id).first()

        # per-user paper status counts
        papers_by_status = {}
        for status in ["unread", "reading", "completed"]:
            count = session.query(ArchivedPaper).filter(
                ArchivedPaper.user_id == user_id,
                ArchivedPaper.read_status == status,
            ).count()
            papers_by_status[status] = count

        topics_count = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id
        ).count()
        topics_completed = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.status == "completed",
        ).count()
        topics_review_later = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.status == "review_later",
        ).count()
        quizzes_count = session.query(ArchivedQuiz).filter(
            ArchivedQuiz.user_id == user_id
        ).count()

        # recent activity for this user
        recent_papers = session.query(SeenPaper).filter(
            SeenPaper.user_id == user_id
        ).order_by(SeenPaper.shown_at.desc()).limit(5).all()
        
        return {
            "lifetime": {
                "papers_seen": stats.total_papers_seen if stats else 0,
                "papers_archived": stats.total_papers_archived if stats else 0,
                "papers_completed": stats.total_papers_completed if stats else 0,
                "topics_reviewed": stats.total_topics_reviewed if stats else 0,
                "topics_completed": topics_completed,
                "topics_review_later": topics_review_later,
                "quizzes_taken": stats.total_quizzes_taken if stats else 0,
                "quiz_accuracy": round(
                    (stats.total_correct_answers / stats.total_quiz_questions * 100) 
                    if stats and stats.total_quiz_questions > 0 else 0, 1
                ),
            },
            "papers_by_status": papers_by_status,
            "streaks": {
                "current": stats.current_streak_days if stats else 0,
                "longest": stats.longest_streak_days if stats else 0,
                "last_activity": stats.last_activity_date.isoformat() if stats and stats.last_activity_date else None,
            },
            "recent_papers": [
                {"title": p.title, "source": p.source, "shown_date": p.shown_date.isoformat()}
                for p in recent_papers
            ],
        }
    finally:
        session.close()


# =============================================================================
# SEEN PAPERS (History)
# =============================================================================

@app.get("/papers/history", tags=["Papers"])
async def get_paper_history(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """Get history of all papers shown to this user."""
    session = get_session()
    try:
        papers = (
            session.query(SeenPaper)
            .filter(SeenPaper.user_id == user_id)
            .order_by(SeenPaper.shown_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = session.query(SeenPaper).filter(SeenPaper.user_id == user_id).count()
        
        return {
            "papers": [
                {
                    "id": p.id,
                    "unique_id": p.unique_id,
                    "title": p.title,
                    "authors": json.loads(p.authors) if p.authors else [],
                    "source": p.source,
                    "url": p.url,
                    "shown_date": p.shown_date.isoformat(),
                    "was_archived": p.was_archived,
                }
                for p in papers
            ],
            "total": total,
        }
    finally:
        session.close()


# =============================================================================
# ARCHIVE ENDPOINTS - PAPERS
# =============================================================================

@app.post("/archive/papers", tags=["Archive"])
async def archive_paper(
    request: ArchivePaperRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Archive a paper to this user's reading list."""
    session = get_session()
    try:
        # generate unique_id if not provided
        unique_id = request.unique_id
        if not unique_id:
            if request.arxiv_id:
                unique_id = f"arxiv:{request.arxiv_id}"
            elif request.doi:
                unique_id = f"doi:{request.doi}"
            elif request.semantic_scholar_id:
                unique_id = f"s2:{request.semantic_scholar_id}"
            else:
                import hashlib
                unique_id = f"hash:{hashlib.md5(request.title.lower().encode()).hexdigest()[:12]}"

        # check if already archived for this user
        existing = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.unique_id == unique_id,
        ).first()
        if existing:
            return {"message": "Paper already archived", "id": existing.id}

        # mark as archived in this user's seen papers if exists
        seen = session.query(SeenPaper).filter(
            SeenPaper.user_id == user_id,
            SeenPaper.unique_id == unique_id,
        ).first()
        if seen:
            seen.was_archived = True

        paper = ArchivedPaper(
            user_id=user_id,
            unique_id=unique_id,
            seen_paper_id=seen.id if seen else None,
            title=request.title,
            authors=json.dumps(request.authors),
            abstract=request.abstract,
            url=request.url,
            pdf_url=request.pdf_url,
            source=request.source,
            primary_category=request.primary_category,
            categories=request.categories,
            relevance_score=request.relevance_score,
            published_date=request.published_date,
            arxiv_id=request.arxiv_id,
            semantic_scholar_id=request.semantic_scholar_id,
            doi=request.doi,
            summary=request.summary,
            key_findings=request.key_findings,
            user_notes=request.user_notes,
            user_rating=request.user_rating,
            read_status=request.read_status or "unread",
            linked_topic_ids=request.linked_topic_ids,
        )
        session.add(paper)

        # update per-user stats (auto-creates the row for first-time users)
        stats = get_or_create_user_stats(user_id, session=session)
        stats.total_papers_archived += 1
        stats.updated_at = datetime.utcnow()

        update_user_streak(user_id=user_id)
        session.commit()
        session.refresh(paper)

        return {"message": "Paper archived successfully", "id": paper.id}
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/archive/papers", tags=["Archive"])
async def get_archived_papers(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """Get all archived papers for this user."""
    session = get_session()
    try:
        query = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id
        ).order_by(ArchivedPaper.archived_at.desc())
        if status:
            query = query.filter(ArchivedPaper.read_status == status)
        papers = query.offset(offset).limit(limit).all()
        total = query.count()
        
        return {
            "papers": [{
                "id": p.id,
                "unique_id": p.unique_id,
                "title": p.title,
                "authors": json.loads(p.authors) if p.authors else [],
                "abstract": p.abstract,
                "url": p.url,
                "pdf_url": p.pdf_url,
                "source": p.source,
                "primary_category": p.primary_category,
                "summary": p.summary,
                "key_findings": p.key_findings,
                "user_notes": p.user_notes,
                "user_rating": p.user_rating,
                "read_status": p.read_status,
                "has_local_pdf": p.has_local_pdf,
                "linked_topic_ids": p.linked_topic_ids,
                "archived_at": p.archived_at.isoformat() if p.archived_at else None,
            } for p in papers],
            "total": total,
        }
    finally:
        session.close()


@app.get("/archive/papers/{paper_id}", tags=["Archive"])
async def get_archived_paper(
    paper_id: int,
    user_id: str = Depends(get_current_user_id),
):
    """Get a specific archived paper owned by this user."""
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.id == paper_id,
        ).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        # Update last accessed
        paper.last_accessed_at = datetime.utcnow()
        session.commit()
        
        return {
            "id": paper.id,
            "unique_id": paper.unique_id,
            "title": paper.title,
            "authors": json.loads(paper.authors) if paper.authors else [],
            "abstract": paper.abstract,
            "url": paper.url,
            "pdf_url": paper.pdf_url,
            "source": paper.source,
            "primary_category": paper.primary_category,
            "categories": paper.categories,
            "summary": paper.summary,
            "key_findings": paper.key_findings,
            "user_notes": paper.user_notes,
            "user_rating": paper.user_rating,
            "read_status": paper.read_status,
            "has_local_pdf": paper.has_local_pdf,
            "local_pdf_path": paper.local_pdf_path,
            "linked_topic_ids": paper.linked_topic_ids,
            "archived_at": paper.archived_at.isoformat() if paper.archived_at else None,
            "completed_at": paper.completed_at.isoformat() if paper.completed_at else None,
        }
    finally:
        session.close()


@app.put("/archive/papers/{paper_id}", tags=["Archive"])
async def update_archived_paper(
    paper_id: int,
    request: UpdatePaperRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Update an archived paper owned by this user."""
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.id == paper_id,
        ).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        if request.user_notes is not None:
            paper.user_notes = request.user_notes
        if request.user_rating is not None:
            paper.user_rating = request.user_rating
        if request.linked_topic_ids is not None:
            paper.linked_topic_ids = request.linked_topic_ids
        if request.read_status is not None:
            old_status = paper.read_status
            paper.read_status = request.read_status
            if request.read_status == "completed" and old_status != "completed":
                paper.completed_at = datetime.utcnow()
                stats = get_or_create_user_stats(user_id, session=session)
                stats.total_papers_completed += 1

        paper.last_accessed_at = datetime.utcnow()
        session.commit()
        return {"message": "Paper updated successfully"}
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.delete("/archive/papers/{paper_id}", tags=["Archive"])
async def delete_archived_paper(
    paper_id: int,
    user_id: str = Depends(get_current_user_id),
):
    """Delete an archived paper owned by this user."""
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.id == paper_id,
        ).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        
        # Delete associated PDF if exists
        if paper.local_pdf_path:
            pdf_path = Path(paper.local_pdf_path)
            if pdf_path.exists():
                pdf_path.unlink()
        
        session.delete(paper)
        session.commit()
        return {"message": "Paper deleted successfully"}
    finally:
        session.close()


# =============================================================================
# PDF UPLOAD/DOWNLOAD
# =============================================================================

@app.post("/archive/papers/{paper_id}/upload-pdf", tags=["Archive"])
async def upload_pdf_to_paper(
    paper_id: int,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id),
):
    """Upload a PDF and attach it to an archived paper owned by this user."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    from .services.storage import get_storage
    storage = get_storage()
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.id == paper_id,
        ).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")

        file_ext = Path(file.filename).suffix
        stored_filename = f"{uuid.uuid4().hex}{file_ext}"
        key = f"papers/{stored_filename}"
        data = await file.read()
        storage.put(key, data, content_type="application/pdf")

        pdf = PaperPDF(
            user_id=user_id,
            archived_paper_id=paper_id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=key,
            file_size_bytes=len(data),
            source="upload",
        )
        session.add(pdf)
        paper.local_pdf_path = key
        paper.has_local_pdf = True
        session.commit()

        return {
            "message": "PDF uploaded successfully",
            "pdf_id": pdf.id,
            "filename": stored_filename,
            "storage_backend": storage.backend,
        }
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.post("/archive/papers/{paper_id}/download-pdf", tags=["Archive"])
async def download_pdf_from_url(
    paper_id: int,
    user_id: str = Depends(get_current_user_id),
):
    """Download PDF from this user's paper's pdf_url and store via the configured backend."""
    from .services.storage import get_storage
    storage = get_storage()
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.id == paper_id,
        ).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        if not paper.pdf_url:
            raise HTTPException(status_code=400, detail="Paper has no PDF URL")
        if paper.has_local_pdf:
            return {"message": "PDF already downloaded", "path": paper.local_pdf_path}

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(paper.pdf_url)
            response.raise_for_status()

        stored_filename = f"{uuid.uuid4().hex}.pdf"
        key = f"papers/{stored_filename}"
        storage.put(key, response.content, content_type="application/pdf")

        pdf = PaperPDF(
            user_id=user_id,
            archived_paper_id=paper_id,
            original_filename=f"{paper.title[:50]}.pdf",
            stored_filename=stored_filename,
            file_path=key,
            file_size_bytes=len(response.content),
            source="download",
            source_url=paper.pdf_url,
        )
        session.add(pdf)
        paper.local_pdf_path = key
        paper.has_local_pdf = True
        session.commit()

        return {
            "message": "PDF downloaded successfully",
            "pdf_id": pdf.id,
            "size_bytes": len(response.content),
            "storage_backend": storage.backend,
        }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to download PDF: {e}")
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/archive/papers/{paper_id}/pdf", tags=["Archive"])
async def get_paper_pdf(
    paper_id: int,
    user_id: str = Depends(get_current_user_id),
):
    """
    Serve the PDF for one of this user's papers.
      - Local backend  -> FileResponse straight from disk.
      - B2 / any backend with signed_url support -> 302 to the presigned URL
        so the backend stays out of the bytes path.
    """
    from .services.storage import get_storage, storage_key_from_legacy_path
    storage = get_storage()
    session = get_session()
    try:
        paper = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.id == paper_id,
        ).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Paper not found")
        if not paper.has_local_pdf or not paper.local_pdf_path:
            raise HTTPException(status_code=404, detail="No PDF available")

        # legacy rows stored an absolute fs path; normalize to a storage key
        key = storage_key_from_legacy_path(paper.local_pdf_path)
        if not storage.exists(key):
            raise HTTPException(
                status_code=404,
                detail=f"PDF not found in {storage.backend} storage (key={key})",
            )

        # prefer presigned URL → browser fetches direct from B2/etc
        url = storage.signed_url(key, expires_seconds=3600)
        if url:
            return RedirectResponse(url=url, status_code=302)

        # fallback: stream from local filesystem
        local = storage.local_path(key)
        if local and local.exists():
            return FileResponse(
                local,
                media_type="application/pdf",
                filename=f"{paper.title[:50]}.pdf",
            )

        raise HTTPException(status_code=500, detail="Storage backend cannot serve this file")
    finally:
        session.close()


@app.post("/papers/upload", tags=["Papers"])
async def upload_standalone_pdf(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    user_id: str = Depends(get_current_user_id),
):
    """Upload a standalone PDF (not attached to an existing paper) for this user."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    session = get_session()
    try:
        # create unique filename
        stored_filename = f"{uuid.uuid4().hex}.pdf"
        file_path = Path("./data/papers") / stored_filename

        # save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_size = file_path.stat().st_size
        paper_title = title or Path(file.filename).stem

        # create a new archived paper entry for this user
        import hashlib
        unique_id = f"upload:{hashlib.md5(f'{paper_title}{datetime.utcnow().isoformat()}'.encode()).hexdigest()[:12]}"

        paper = ArchivedPaper(
            user_id=user_id,
            unique_id=unique_id,
            title=paper_title,
            authors=json.dumps([]),
            source="upload",
            url="",
            local_pdf_path=str(file_path),
            has_local_pdf=True,
            read_status="unread",
        )
        session.add(paper)
        session.flush()

        # create PDF record
        pdf = PaperPDF(
            user_id=user_id,
            archived_paper_id=paper.id,
            original_filename=file.filename,
            stored_filename=stored_filename,
            file_path=str(file_path),
            file_size_bytes=file_size,
            source="upload",
        )
        session.add(pdf)

        # update per-user stats (auto-creates the row for first-time users)
        stats = get_or_create_user_stats(user_id, session=session)
        stats.total_papers_archived += 1

        session.commit()
        
        return {
            "message": "PDF uploaded and paper created",
            "paper_id": paper.id,
            "title": paper_title,
        }
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


# =============================================================================
# ARCHIVE ENDPOINTS - TOPICS
# =============================================================================

@app.post("/archive/topics", tags=["Archive"])
async def archive_topic_review(
    request: ArchiveTopicRequest,
    user_id: str = Depends(get_current_user_id),
):
    session = get_session()
    try:
        existing = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.topic_id == request.topic_id,
        ).first()
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
            if request.linked_paper_ids:
                existing.linked_paper_ids = request.linked_paper_ids
            if request.status:
                existing.status = request.status
                if request.status == "completed" and not existing.completed_at:
                    existing.completed_at = datetime.utcnow()
            session.commit()

            stats = get_or_create_user_stats(user_id, session=session)
            stats.total_topics_reviewed += 1

            return {"message": "Topic review updated", "id": existing.id, "review_count": existing.review_count}

        topic = ArchivedTopicReview(
            user_id=user_id,
            topic_id=request.topic_id,
            topic_name=request.topic_name,
            course_id=request.course_id,
            course_name=request.course_name,
            week_covered=request.week_covered,
            review_content=request.review_content,
            key_points=request.key_points,
            connections=request.connections,
            practice_suggestions=request.practice_suggestions,
            key_concepts=request.key_concepts,
            user_notes=request.user_notes,
            confidence_level=request.confidence_level,
            linked_paper_ids=request.linked_paper_ids,
            status=request.status or "active",
        )
        if request.status == "completed":
            topic.completed_at = datetime.utcnow()

        session.add(topic)

        stats = session.query(UserStats).filter(UserStats.user_id == user_id).first()
        if stats:
            stats.total_topics_reviewed += 1

        update_user_streak(user_id=user_id)
        session.commit()
        session.refresh(topic)
        return {"message": "Topic review archived", "id": topic.id}
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/archive/topics", tags=["Archive"])
async def get_archived_topics(
    limit: int = 50,
    offset: int = 0,
    course_id: Optional[str] = None,
    status: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    session = get_session()
    try:
        query = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id
        ).order_by(ArchivedTopicReview.last_reviewed_at.desc())
        if course_id:
            query = query.filter(ArchivedTopicReview.course_id == course_id)
        if status:
            query = query.filter(ArchivedTopicReview.status == status)
        topics = query.offset(offset).limit(limit).all()
        total = query.count()
        return {
            "topics": [{
                "id": t.id,
                "topic_id": t.topic_id,
                "topic_name": t.topic_name,
                "course_id": t.course_id,
                "course_name": t.course_name,
                "week_covered": t.week_covered,
                "key_points": t.key_points,
                "user_notes": t.user_notes,
                "confidence_level": t.confidence_level,
                "review_count": t.review_count,
                "status": t.status,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
                "linked_paper_ids": t.linked_paper_ids,
                "last_reviewed_at": t.last_reviewed_at.isoformat() if t.last_reviewed_at else None,
            } for t in topics],
            "total": total,
        }
    finally:
        session.close()


@app.put("/archive/topics/{topic_db_id}", tags=["Archive"])
async def update_archived_topic(
    topic_db_id: int,
    request: UpdateTopicRequest,
    user_id: str = Depends(get_current_user_id),
):
    session = get_session()
    try:
        topic = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.id == topic_db_id,
        ).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        if request.user_notes is not None:
            topic.user_notes = request.user_notes
        if request.confidence_level is not None:
            topic.confidence_level = request.confidence_level
        if request.linked_paper_ids is not None:
            topic.linked_paper_ids = request.linked_paper_ids
        if request.status is not None:
            topic.status = request.status
            if request.status == "completed" and not topic.completed_at:
                topic.completed_at = datetime.utcnow()
            elif request.status != "completed":
                topic.completed_at = None
        session.commit()
        return {"message": "Topic updated"}
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.delete("/archive/topics/{topic_db_id}", tags=["Archive"])
async def delete_archived_topic(
    topic_db_id: int,
    user_id: str = Depends(get_current_user_id),
):
    session = get_session()
    try:
        topic = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.id == topic_db_id,
        ).first()
        if not topic:
            raise HTTPException(status_code=404, detail="Topic not found")
        session.delete(topic)
        session.commit()
        return {"message": "Topic deleted"}
    finally:
        session.close()


# =============================================================================
# TOPIC STATUS ENDPOINTS (New)
# =============================================================================

@app.put("/topics/{topic_id}/status", tags=["Topics"])
async def update_topic_status(
    topic_id: str,
    request: TopicStatusRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Set a topic's lifecycle status for this user: active, completed, or review_later.
    Creates an archived record if one doesn't exist yet.
    """
    if request.status not in ("active", "completed", "review_later"):
        raise HTTPException(status_code=400, detail="Status must be 'active', 'completed', or 'review_later'")

    session = get_session()
    try:
        existing = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.topic_id == topic_id,
        ).first()

        if existing:
            existing.status = request.status
            if request.status == "completed" and not existing.completed_at:
                existing.completed_at = datetime.utcnow()
            elif request.status != "completed":
                existing.completed_at = None
            session.commit()
            return {"message": f"Topic status updated to '{request.status}'", "id": existing.id}

        # no archived record yet for this user — create a minimal one from the Topic row
        topic = _get_topic_or_404(topic_id)
        new_record = ArchivedTopicReview(
            user_id=user_id,
            topic_id=topic.id,
            topic_name=topic.name,
            course_id=topic.stream,                              # stream lives in course_id slot
            course_name=_stream_display_name(topic.stream),
            week_covered=None,
            key_concepts=topic.key_concepts or [],
            review_content="",
            key_points=[],
            connections=[],
            practice_suggestions=[],
            status=request.status,
            review_count=0,
        )
        if request.status == "completed":
            new_record.completed_at = datetime.utcnow()
        
        session.add(new_record)
        session.commit()
        session.refresh(new_record)
        return {"message": f"Topic status set to '{request.status}'", "id": new_record.id}
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/topics/random-review", tags=["Topics"])
async def get_random_topic_review(
    exclude: Optional[str] = None,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate a review for a topic randomly chosen from this user's active scope.

    Selection rules (in order):
      - exclude topics marked completed
      - avoid topics reviewed in the last 3 days
      - prioritize topics marked review_later
      - fall back to anything not completed
    Optional `exclude` param: comma-separated topic ids to skip ("new topic" cycling).
    """
    from .database import get_topics_for_scope
    from .services import ContentGeneratorService

    scope_topics = get_topics_for_scope(user_id=user_id)
    if not scope_topics:
        raise HTTPException(status_code=404, detail="No topics in active scope")

    completed_ids = get_completed_topic_ids(user_id=user_id)
    recently_reviewed_ids = get_recently_reviewed_topic_ids(user_id=user_id, days=3)
    review_later_ids = get_review_later_topic_ids(user_id=user_id)
    exclude_ids = set(exclude.split(",")) if exclude else set()

    topic = _select_topic_from_scope(
        scope_topics, completed_ids, recently_reviewed_ids, review_later_ids, exclude_ids
    )
    if not topic:
        raise HTTPException(
            status_code=404,
            detail="No available topics to review (all may be completed or recently reviewed)",
        )

    topic_dict = _topic_to_dict(topic)
    course_dict = _topic_pseudo_course(topic)

    generator = ContentGeneratorService()
    try:
        review = await generator.generate_topic_review(topic_dict, course_dict)
        # preserve list shape for API compat
        return {"topic_reviews": [{"topic": topic_dict, "review": review}]}
    finally:
        await generator.close()


@app.get("/topics/status-summary", tags=["Topics"])
async def get_topic_status_summary(user_id: str = Depends(get_current_user_id)):
    """
    Summary of topic statuses for this user across all topics in the Topic table.
    Counts use the universe of active topics, not the scope-filtered view.
    """
    from .database import Topic as TopicModel

    session = get_session()
    try:
        total = session.query(TopicModel).filter(TopicModel.active.is_(True)).count()
    finally:
        session.close()

    completed_ids = get_completed_topic_ids(user_id=user_id)
    review_later_ids = get_review_later_topic_ids(user_id=user_id)
    completed = len(completed_ids)
    review_later = len(review_later_ids)
    active = max(0, total - completed - review_later)

    return {
        "total_topics": total,
        "active": active,
        "review_later": review_later,
        "completed": completed,
        "completion_percentage": round((completed / total * 100) if total > 0 else 0, 1),
    }


# =============================================================================
# ARCHIVE ENDPOINTS - QUIZZES
# =============================================================================

@app.post("/archive/quizzes", tags=["Archive"])
async def archive_quiz(
    request: ArchiveQuizRequest,
    user_id: str = Depends(get_current_user_id),
):
    session = get_session()
    try:
        quiz = ArchivedQuiz(
            user_id=user_id,
            topics=request.topics,
            topic_ids=request.topic_ids,
            total_questions=request.total_questions,
            total_points=request.total_points,
            score_earned=request.score_earned,
            percentage=request.percentage,
            questions=request.questions,
            duration_seconds=request.duration_seconds,
        )
        session.add(quiz)

        stats = get_or_create_user_stats(user_id, session=session)
        stats.total_quizzes_taken += 1
        stats.total_quiz_questions += request.total_questions
        correct = sum(1 for q in request.questions if q.get("result", {}).get("correct", False))
        stats.total_correct_answers += correct

        update_user_streak(user_id=user_id)
        session.commit()
        session.refresh(quiz)
        return {"message": "Quiz archived", "id": quiz.id}
    except HTTPException:
        # don't let the catch-all swallow 4xx/404 raised inside the try block
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/archive/quizzes", tags=["Archive"])
async def get_archived_quizzes(
    limit: int = 50,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    session = get_session()
    try:
        query = session.query(ArchivedQuiz).filter(
            ArchivedQuiz.user_id == user_id
        ).order_by(ArchivedQuiz.taken_at.desc())
        quizzes = query.offset(offset).limit(limit).all()
        total = query.count()
        return {
            "quizzes": [{
                "id": q.id,
                "topics": q.topics,
                "total_questions": q.total_questions,
                "total_points": q.total_points,
                "score_earned": q.score_earned,
                "percentage": q.percentage,
                "duration_seconds": q.duration_seconds,
                "taken_at": q.taken_at.isoformat() if q.taken_at else None,
            } for q in quizzes],
            "total": total,
        }
    finally:
        session.close()


@app.delete("/archive/quizzes/{quiz_id}", tags=["Archive"])
async def delete_archived_quiz(
    quiz_id: int,
    user_id: str = Depends(get_current_user_id),
):
    session = get_session()
    try:
        quiz = session.query(ArchivedQuiz).filter(
            ArchivedQuiz.user_id == user_id,
            ArchivedQuiz.id == quiz_id,
        ).first()
        if not quiz:
            raise HTTPException(status_code=404, detail="Quiz not found")
        session.delete(quiz)
        session.commit()
        return {"message": "Quiz deleted"}
    finally:
        session.close()


@app.get("/archive/stats", tags=["Archive"])
async def get_archive_stats(user_id: str = Depends(get_current_user_id)):
    session = get_session()
    try:
        papers_total = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id
        ).count()
        papers_completed = session.query(ArchivedPaper).filter(
            ArchivedPaper.user_id == user_id,
            ArchivedPaper.read_status == "completed",
        ).count()
        topics_count = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id
        ).count()
        topics_completed = session.query(ArchivedTopicReview).filter(
            ArchivedTopicReview.user_id == user_id,
            ArchivedTopicReview.status == "completed",
        ).count()
        total_reviews = sum(
            r[0] for r in session.query(ArchivedTopicReview.review_count).filter(
                ArchivedTopicReview.user_id == user_id
            ).all()
        ) or 0
        quizzes_count = session.query(ArchivedQuiz).filter(
            ArchivedQuiz.user_id == user_id
        ).count()
        quiz_scores = [
            s[0] for s in session.query(ArchivedQuiz.percentage).filter(
                ArchivedQuiz.user_id == user_id
            ).all()
        ]
        avg_score = sum(quiz_scores) / len(quiz_scores) if quiz_scores else 0
        
        return {
            "papers": {"total": papers_total, "completed": papers_completed},
            "topics": {"unique_topics": topics_count, "total_reviews": total_reviews, "completed": topics_completed},
            "quizzes": {"total": quizzes_count, "average_score": round(avg_score, 1)},
        }
    finally:
        session.close()


# =============================================================================
# PAPER DISCOVERY (with seen tracking)
# =============================================================================

@app.get("/papers/discover", tags=["Papers"])
async def discover_papers(
    max_results: int = 10,
    days_back: int = 30,
    user_id: str = Depends(get_current_user_id),
):
    from .services import PaperDiscoveryService

    # exclude papers this user has already seen
    seen_ids = get_seen_paper_ids(user_id=user_id)

    service = PaperDiscoveryService(user_id=user_id)
    try:
        papers = await service.discover_papers(max_results=max_results + len(seen_ids), days_back=days_back)

        # filter out seen papers
        new_papers = [p for p in papers if p.unique_id not in seen_ids][:max_results]

        return {
            "count": len(new_papers),
            "papers": [p.to_dict() for p in new_papers],
            "filtered_seen": len(papers) - len(new_papers),
        }
    finally:
        await service.close()


@app.get("/papers/daily", tags=["Papers"])
async def get_daily_paper(user_id: str = Depends(get_current_user_id)):
    from .services import PaperDiscoveryService, ContentGeneratorService

    seen_ids = list(get_seen_paper_ids(user_id=user_id))

    discovery = PaperDiscoveryService(user_id=user_id)
    generator = ContentGeneratorService()

    try:
        paper = await discovery.select_daily_paper(seen_ids=seen_ids, days_back=30)

        if not paper:
            return {"message": "No new papers found", "paper": None}

        # mark as seen for this user
        paper_dict = paper.to_dict()
        paper_dict["unique_id"] = paper.unique_id
        mark_paper_as_seen(paper_dict, user_id=user_id)

        summary = await generator.generate_paper_summary(paper)

        return {"paper": paper.to_dict(), "summary": summary}
    finally:
        await discovery.close()
        await generator.close()


# =============================================================================
# TOPICS & QUIZ (existing endpoints)
# =============================================================================

# NOTE: GET /topics is now served by backend.api.topics.topics_router
# (returns Topic-table rows, not courses.yaml topics). The endpoints below
# still read from courses.yaml and will be refactored to the new Topic
# table in a follow-up task.

@app.get("/topics/{topic_id}/review", tags=["Topics"])
async def get_topic_review(topic_id: str):
    """Generate a review for a topic from the Topic table."""
    from .services import ContentGeneratorService

    topic = _get_topic_or_404(topic_id)
    topic_dict = _topic_to_dict(topic)
    course_dict = _topic_pseudo_course(topic)

    generator = ContentGeneratorService()
    try:
        review = await generator.generate_topic_review(topic_dict, course_dict)
        return {"topic": topic_dict, "review": review}
    finally:
        await generator.close()


@app.get("/quiz/generate/{topic_id}", tags=["Quiz"])
async def generate_quiz(topic_id: str, count: int = 5, difficulty: str = "medium"):
    """Generate a quiz for one topic from the Topic table."""
    from .services import ContentGeneratorService

    topic = _get_topic_or_404(topic_id)
    topic_dict = _topic_to_dict(topic)
    course_dict = _topic_pseudo_course(topic)

    generator = ContentGeneratorService()
    try:
        questions = await generator.generate_quiz_questions(
            topic_dict, course_dict, count=count, difficulty=difficulty
        )
        questions_display = [{
            "id": q["id"], "topic_id": q["topic_id"], "topic_name": topic.name,
            "course_name": course_dict["name"], "question_type": q["question_type"],
            "question_text": q["question_text"], "options": q.get("options"),
            "difficulty": q["difficulty"], "points": q["points"],
        } for q in questions]
        app.state.current_questions = {q["id"]: q for q in questions}
        return {
            "topic": topic.name,
            "course": course_dict["name"],
            "questions": questions_display,
            "total_points": sum(q["points"] for q in questions),
        }
    finally:
        await generator.close()


@app.post("/quiz/regenerate", tags=["Quiz"])
async def regenerate_quiz(
    count: int = 5,
    difficulty: str = "medium",
    max_topics: int = 3,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate a multi-topic quiz drawing from this user's active scope.

    To keep latency reasonable, we cap at `max_topics` (default 3) randomly
    chosen from the scope rather than hitting the LLM once per topic. With
    7+ active topics, the per-topic loop otherwise compounds to several
    minutes of sequential LLM calls.
    """
    from .database import get_topics_for_scope
    from .services import ContentGeneratorService

    scope_topics = get_topics_for_scope(user_id=user_id)
    if not scope_topics:
        raise HTTPException(status_code=404, detail="No topics in active scope")

    # cap the topic pool — random pick keeps quiz variety across reloads
    if len(scope_topics) > max_topics:
        scope_topics = random.sample(scope_topics, max_topics)

    generator = ContentGeneratorService()
    try:
        all_questions = []
        questions_per_topic = max(1, count // len(scope_topics))
        for topic in scope_topics:
            topic_dict = _topic_to_dict(topic)
            course_dict = _topic_pseudo_course(topic)
            questions = await generator.generate_quiz_questions(
                topic_dict, course_dict,
                count=questions_per_topic, difficulty=difficulty,
            )
            for q in questions:
                q["topic_name"] = topic.name
                q["course_name"] = course_dict["name"]
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

        return {
            "topics": [t.name for t in scope_topics],
            "questions": questions_display,
            "total_points": sum(q["points"] for q in all_questions),
        }
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
# DAILY CONTENT (with smart topic rotation)
# =============================================================================

@app.get("/daily", tags=["Daily"])
async def get_daily_content(
    refresh: str = "",
    user_id: str = Depends(get_current_user_id),
):
    """
    Daily content: one paper + one topic review + a quiz, all scoped to
    this user's active topics. Cached per-day in `daily_content_cache`.

    Body lives in `services/daily_content.generate_daily_content` so the
    APScheduler nightly job can call the same code path.
    """
    from .services.daily_content import generate_daily_content, VALID_REFRESH

    try:
        result = await generate_daily_content(refresh=refresh, user_id=user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # rehydrate app.state.current_questions so /quiz/answer can look up by id
    quiz_full = result.pop("_quiz_full", [])
    app.state.current_questions = {q["id"]: q for q in quiz_full}
    return result



# =============================================================================
# ROUTER MOUNTING (must come AFTER all @app.get/post/put decorators in this
# file so that specific paths like /topics/status-summary and
# /topics/{id}/review take precedence over the router's catch-all
# /topics/{topic_id}.)
# =============================================================================

from .api.topics import topics_router, scope_router
from .api.push import push_router
from .api.admin import admin_router
from .api.admin_invites import admin_invites_router
from .api.admin_approvals import admin_approvals_router
from .api.admin_accounts import admin_accounts_router
from .api.admin_audit import admin_audit_router
from .api.notifications import notifications_router
from .api.auth import auth_router
from .api.onboarding import onboarding_router
app.include_router(topics_router)
app.include_router(scope_router)
app.include_router(push_router)
app.include_router(admin_router)
app.include_router(admin_invites_router)
app.include_router(admin_approvals_router)
app.include_router(admin_accounts_router)
app.include_router(admin_audit_router)
app.include_router(notifications_router)
app.include_router(auth_router)
app.include_router(onboarding_router)


# =============================================================================
# ADMIN / SCHEDULER INSPECTION
# =============================================================================

@app.get("/admin/scheduler/jobs", tags=["Admin"])
def admin_list_scheduler_jobs():
    """List active APScheduler jobs (for debugging)."""
    from .services.scheduler import list_jobs
    return {"jobs": list_jobs()}


@app.post("/admin/scheduler/run/{job_id}", tags=["Admin"])
async def admin_run_scheduler_job(job_id: str):
    """Manually fire a scheduled job by id. Useful for testing nightly logic without waiting."""
    from .services.scheduler import trigger_now
    return await trigger_now(job_id)


# =============================================================================
# DEEP HEALTH CHECK
# =============================================================================

@app.get("/health/deep", tags=["Core"])
async def health_check_deep():
    """
    Per-subsystem health with latency. Returns 200 only when all CRITICAL
    subsystems pass (DB + default LLM provider). Storage and push are
    informational — degraded but not fatal.

    Use the lightweight /health for platform health checks (Railway, CF);
    use this when you want to see exactly which dep is unhealthy.
    """
    import time as _time
    from fastapi.responses import JSONResponse
    from sqlalchemy import text as _sql_text

    settings = get_settings()
    out: dict[str, dict] = {}

    def _ping(name: str, fn) -> dict:
        t0 = _time.perf_counter()
        try:
            detail = fn() or {}
            ok = True
            error: Optional[str] = None
        except Exception as e:  # noqa: BLE001
            ok = False
            detail = {}
            error = f"{type(e).__name__}: {e}"[:200]
        return {
            "ok": ok,
            "latency_ms": round((_time.perf_counter() - t0) * 1000, 1),
            **({"error": error} if error else {}),
            **detail,
        }

    # DB
    def _check_db():
        engine = get_session().get_bind()
        with engine.connect() as conn:
            conn.execute(_sql_text("SELECT 1"))
        return {"url_scheme": str(engine.url.drivername)}
    out["db"] = _ping("db", _check_db)

    # default LLM provider — just verify the API key is present (don't burn tokens)
    def _check_anthropic():
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        return {"model": settings.claude_model}
    out["llm.anthropic"] = _ping("llm.anthropic", _check_anthropic)

    # optional LLM providers
    def _check_gemini():
        if not settings.gemini_api_key:
            return {"configured": False}
        return {"configured": True, "model": settings.gemini_model}
    out["llm.gemini"] = _ping("llm.gemini", _check_gemini)

    # storage backend (head_bucket for B2, dir-exists for local)
    def _check_storage():
        from .services.storage import get_storage
        s = get_storage()
        if s.backend == "b2":
            # exists() does a head_object which would 404 — use the bucket-level head
            # by listing a single key via the private boto3 client.
            s._client.head_bucket(Bucket=s.bucket)  # type: ignore[attr-defined]
            return {"backend": "b2", "bucket": s.bucket}
        # local: just confirm root dir exists and is writable
        root = s.local_path("__healthcheck__")
        if root is None:
            return {"backend": s.backend}
        root.parent.mkdir(parents=True, exist_ok=True)
        return {"backend": "local", "root": str(root.parent)}
    out["storage"] = _ping("storage", _check_storage)

    # web push setup (just key presence)
    def _check_vapid():
        if not (settings.vapid_public_key and settings.vapid_private_key and settings.vapid_subject):
            return {"configured": False}
        return {"configured": True, "subject": settings.vapid_subject}
    out["push.vapid"] = _ping("push.vapid", _check_vapid)

    # arXiv reachability (lightweight HEAD-equivalent)
    async def _check_arxiv_async():
        import httpx
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as c:
            r = await c.get("https://export.arxiv.org/api/query?search_query=all:test&max_results=1")
            r.raise_for_status()
            return {"status_code": r.status_code}
    arxiv_t0 = (lambda: 0)()
    import time as _time2
    arxiv_t0 = _time2.perf_counter()
    try:
        detail = await _check_arxiv_async()
        out["arxiv"] = {
            "ok": True,
            "latency_ms": round((_time2.perf_counter() - arxiv_t0) * 1000, 1),
            **detail,
        }
    except Exception as e:  # noqa: BLE001
        out["arxiv"] = {
            "ok": False,
            "latency_ms": round((_time2.perf_counter() - arxiv_t0) * 1000, 1),
            "error": f"{type(e).__name__}: {e}"[:200],
        }

    # scheduler
    def _check_scheduler():
        from .services.scheduler import list_jobs
        jobs = list_jobs()
        return {"running": len(jobs) > 0, "job_count": len(jobs)}
    out["scheduler"] = _ping("scheduler", _check_scheduler)

    critical = ("db", "llm.anthropic")
    status = "healthy" if all(out[k]["ok"] for k in critical) else "degraded"
    payload = {"status": status, "timestamp": date.today().isoformat(), "subsystems": out}
    return JSONResponse(
        content=payload,
        status_code=200 if status == "healthy" else 503,
    )
