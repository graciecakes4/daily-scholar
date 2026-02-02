# Daily Scholar 📚

A personalized daily learning system for doctoral students and data scientists. Automatically delivers:
- **Fresh research papers** matching your interests
- **Topic reviews** from your current courses  
- **Interactive quizzes** with spaced repetition
- **Supplementary resources** via web search

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DAILY SCHOLAR                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         FRONTEND (Next.js)                            │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │  │
│  │  │Dashboard│  │ Paper   │  │ Review  │  │  Quiz   │  │Settings │   │  │
│  │  │  Home   │  │ Reader  │  │  Mode   │  │  Mode   │  │ Upload  │   │  │
│  │  └─────────┘  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      BACKEND API (FastAPI)                            │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐    │  │
│  │  │  /papers   │  │  /topics   │  │  /quiz     │  │  /upload   │    │  │
│  │  │  endpoint  │  │  endpoint  │  │  endpoint  │  │  endpoint  │    │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         SERVICES LAYER                                │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │  │
│  │  │ Paper Discovery │  │ Content Gen     │  │ Quiz Engine     │      │  │
│  │  │ - arXiv API     │  │ - Claude API    │  │ - Spaced Rep    │      │  │
│  │  │ - Semantic Sch. │  │ - Summarization │  │ - Scoring       │      │  │
│  │  │ - CORE API      │  │ - Q&A Gen       │  │ - Progress      │      │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                         │
│                                    ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                          DATA LAYER                                   │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │  │
│  │  │ SQLite Database │  │ File Storage    │  │ Config (YAML)   │      │  │
│  │  │ - seen_papers   │  │ - course docs   │  │ - interests     │      │  │
│  │  │ - quiz_history  │  │ - uploaded PDFs │  │ - courses       │      │  │
│  │  │ - progress      │  │                 │  │ - schedule      │      │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
daily-scholar/
├── README.md                 # This file
├── backend/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── database.py          # SQLite database setup
│   ├── models.py            # Pydantic models (data validation)
│   ├── services/
│   │   ├── paper_discovery.py    # arXiv, Semantic Scholar APIs
│   │   ├── content_generator.py  # Claude API integration
│   │   ├── quiz_engine.py        # Quiz generation & scoring
│   │   └── file_processor.py     # PDF/document parsing
│   └── routers/
│       ├── papers.py        # Paper-related endpoints
│       ├── topics.py        # Topic review endpoints
│       ├── quiz.py          # Quiz endpoints
│       └── upload.py        # File upload endpoints
├── frontend/
│   └── (Next.js application)
├── config/
│   ├── interests.yaml       # Your research interests
│   └── courses.yaml         # Your course materials
├── scripts/
│   ├── daily_job.py         # Scheduled daily content generation
│   └── setup_db.py          # Database initialization
├── docs/
│   └── LEARNING_GUIDE.md    # Explains each component for learning
├── requirements.txt         # Python dependencies
└── .env.example             # Environment variables template
```

## Quick Start

### 1. Clone and Setup

```bash
cd daily-scholar
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Configure Your Interests & Courses

Edit `config/interests.yaml` and `config/courses.yaml` with your information.

### 4. Initialize Database

```bash
python scripts/setup_db.py
```

### 5. Run the Backend

```bash
cd backend
uvicorn main:app --reload
```

### 6. Run the Frontend

```bash
cd frontend
npm install
npm run dev
```

## API Keys Required

- **Anthropic API** (Claude) - for content generation
- **Semantic Scholar API** (optional, has free tier without key)
- **CORE API** (optional, for broader paper access)

## Learning Path

This project is designed to help you learn:

1. **Week 1-2**: Understand the architecture, run the system
2. **Week 3-4**: Modify configurations, add new paper sources
3. **Week 5-6**: Extend the quiz system, add new question types
4. **Week 7-8**: Build new frontend features
5. **Ongoing**: Full ownership - add whatever features you want!

See `docs/LEARNING_GUIDE.md` for detailed explanations of each component.

## Tech Stack

**Backend:**
- Python 3.11+
- FastAPI (modern, fast web framework)
- SQLite (simple, file-based database)
- Pydantic (data validation)
- httpx (async HTTP client)

**Frontend:**
- Next.js 14 (React framework)
- Tailwind CSS (utility-first styling)
- TypeScript (type safety)

**External APIs:**
- arXiv API (physics, CS, math papers)
- Semantic Scholar API (broad paper discovery)
- Anthropic Claude API (content generation)

**URLS**
- API Root: http://localhost:8000
    - API Docs: http://localhost:8000/docs
    - API Redoc: http://localhost:8000/redoc
    - API Health: http://localhost:8000/health
    - API Papers: http://localhost:8000/papers
    - API Topics: http://localhost:8000/topics
    - API Quiz: http://localhost:8000/quiz
    - API Upload: http://localhost:8000/upload
- Frontend 
    - Dashboard: http://localhost:3000  
    - Paper Reader: http://localhost:3000/paper-reader
    - Review Mode: http://localhost:3000/review-mode
    - Quiz Mode: http://localhost:3000/quiz-mode
    - Settings: http://localhost:3000/settings 
    - Upload: http://localhost:3000/upload
