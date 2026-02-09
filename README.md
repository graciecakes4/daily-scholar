# Daily Scholar 📚

A personalized daily learning system for doctoral students and data scientists. Automatically delivers:
- **Fresh research papers** matching your interests
- **Topic reviews** from your current courses  
- **Interactive quizzes** with spaced repetition
- **Supplementary resources** via web search

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Directory Structure](#directory-structure)
3. [Installation Guide](#installation-guide)
4. [Operating the Application](#operating-the-application)
5. [API Reference](#api-reference)
6. [Configuration](#configuration)
7. [Tech Stack](#tech-stack)
8. [Learning Path](#learning-path)
9. [Troubleshooting](#troubleshooting)

---

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

---

## Directory Structure

```
daily-scholar/
├── README.md                 # This file
├── .env                      # Environment variables (API keys) - DO NOT COMMIT
├── .env.example              # Template for environment variables
├── .gitignore                # Git ignore rules
├── requirements.txt          # Python dependencies
│
├── backend/
│   ├── __init__.py
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration management
│   ├── database.py          # SQLite database setup
│   ├── models.py            # Pydantic models (data validation)
│   └── services/
│       ├── __init__.py
│       ├── paper_discovery.py    # arXiv, Semantic Scholar APIs
│       └── content_generator.py  # Claude API integration
│
├── frontend/
│   ├── package.json         # Node.js dependencies
│   ├── tsconfig.json        # TypeScript configuration
│   ├── tailwind.config.js   # Tailwind CSS configuration
│   ├── postcss.config.js    # PostCSS configuration
│   ├── next.config.js       # Next.js configuration
│   ├── app/
│   │   ├── layout.tsx       # Root layout component
│   │   ├── page.tsx         # Main dashboard page
│   │   └── globals.css      # Global styles
│   └── lib/
│       └── api.ts           # API client functions
│
├── config/
│   ├── interests.yaml       # Your research interests
│   └── courses.yaml         # Your course materials
│
├── scripts/
│   └── setup_db.py          # Database initialization
│
├── docs/
│   └── LEARNING_GUIDE.md    # Explains each component for learning
│
├── data/                    # SQLite database (auto-generated)
│   └── daily_scholar.db
│
└── uploads/                 # Uploaded course materials
    └── course_materials/
        ├── data-engineering/
        │   └── textbooks/
        └── dl-nlp/
            └── textbooks/
```

---

## Installation Guide

### Prerequisites

- **Python 3.9+** (`python3 --version`)
- **Node.js 18+** (`node --version`)
- **npm** (`npm --version`)
- **Git** (`git --version`)

### Step 1: Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/daily-scholar.git
cd daily-scholar
```

### Step 2: Set Up Python Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# Install Python dependencies
pip install -r requirements.txt
```

### Step 3: Configure Environment Variables

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your API keys
nano .env  # or open in your preferred editor
```

**Required API Keys:**

| Key | Required | How to Get |
|-----|----------|------------|
| `ANTHROPIC_API_KEY` | ✅ Yes | https://console.anthropic.com/ |
| `SEMANTIC_SCHOLAR_API_KEY` | ❌ Optional | https://www.semanticscholar.org/product/api |

### Step 4: Configure Your Interests & Courses

Edit the YAML configuration files:

```bash
# Edit your research interests
nano config/interests.yaml

# Edit your course materials
nano config/courses.yaml
```

### Step 5: Set Up Course Materials Directory

```bash
# Create directories for your textbooks and notes
mkdir -p uploads/course_materials/data-engineering/textbooks
mkdir -p uploads/course_materials/dl-nlp/textbooks

# Copy your textbooks (adjust paths as needed)
cp /path/to/your/textbook.pdf uploads/course_materials/data-engineering/textbooks/
```

### Step 6: Initialize the Database

```bash
python scripts/setup_db.py
```

### Step 7: Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### Step 8: Verify Installation

```bash
# Check configuration status
source venv/bin/activate
uvicorn backend.main:app --reload &

# Wait a few seconds, then test
curl http://localhost:8000/health
curl http://localhost:8000/config/status

# Stop the server
kill %1
```

You should see `{"status":"healthy"}` and a config status showing your interests and courses loaded.

---

## Operating the Application

### Starting the Application

You need **two terminal windows** - one for the backend, one for the frontend.

#### Terminal 1: Start Backend API

```bash
cd ~/daily-scholar
source venv/bin/activate
uvicorn backend.main:app --reload
```

✅ **Backend is running when you see:**
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

#### Terminal 2: Start Frontend

```bash
cd ~/daily-scholar/frontend
npm run dev
```

✅ **Frontend is running when you see:**
```
✓ Ready in Xs
```

### Accessing the Application

| URL | Description |
|-----|-------------|
| http://localhost:3000 | **Main Dashboard** - Start here! |
| http://localhost:8000/docs | **Swagger UI** - Interactive API testing |
| http://localhost:8000/redoc | **ReDoc** - API documentation |
| http://localhost:8000/health | Health check |
| http://localhost:8000/config/status | Configuration status |

### Daily Usage

1. **Open the dashboard** at http://localhost:3000
2. **View today's content** - paper summaries, topic reviews, quiz questions
3. **Take the quiz** - submit answers and get AI-powered feedback
4. **Explore resources** - follow suggested readings and tutorials

### Using the API Directly (Swagger UI)

1. Go to http://localhost:8000/docs
2. Click on any endpoint (e.g., `GET /daily`)
3. Click **"Try it out"**
4. Click **"Execute"**
5. View the response below

### Stopping the Application

- **Backend**: Press `Ctrl+C` in Terminal 1
- **Frontend**: Press `Ctrl+C` in Terminal 2

### Restarting After Computer Restart

```bash
# Terminal 1
cd ~/daily-scholar
source venv/bin/activate
uvicorn backend.main:app --reload

# Terminal 2
cd ~/daily-scholar/frontend
npm run dev
```

---

## API Reference

### Core Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/config/status` | Configuration status |
| `GET` | `/daily` | Get today's paper, reviews, and quiz |
| `GET` | `/papers/discover` | Discover new papers based on interests |
| `GET` | `/papers/daily` | Get today's selected paper |
| `GET` | `/topics` | List all course topics |
| `GET` | `/topics/{topic_id}/review` | Get review for a specific topic |
| `GET` | `/quiz/generate/{topic_id}` | Generate quiz for a topic |
| `POST` | `/quiz/answer` | Submit quiz answer for evaluation |

### Example API Calls

```bash
# Health check
curl http://localhost:8000/health

# Get configuration status
curl http://localhost:8000/config/status

# Get today's content (paper + reviews + quiz)
curl http://localhost:8000/daily

# Discover papers matching your interests
curl http://localhost:8000/papers/discover

# Get all topics
curl http://localhost:8000/topics

# Generate quiz for a specific topic
curl http://localhost:8000/quiz/generate/dlnlp-intro-ann
```

---

## Configuration

### interests.yaml

Defines your research interests for paper discovery:

```yaml
interests:
  primary:
    - name: "Machine Learning"
      keywords:
        - "deep learning"
        - "neural networks"
      weight: 2.0
      arxiv_categories: ["cs.LG", "stat.ML"]
```

### courses.yaml

Defines your courses and topics for reviews/quizzes:

```yaml
courses:
  - id: "dl-nlp"
    name: "Deep Learning and NLP"
    topics:
      - id: "dlnlp-intro-ann"
        name: "Introduction to ANNs"
        key_concepts:
          - "artificial neural networks"
          - "neurons and layers"
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Backend** | Python 3.9+ | Core language |
| | FastAPI | Web framework |
| | SQLite | Database |
| | Pydantic | Data validation |
| | httpx | HTTP client |
| **Frontend** | Next.js 14+ | React framework |
| | TypeScript | Type safety |
| | Tailwind CSS | Styling |
| **APIs** | Anthropic Claude | Content generation |
| | arXiv | Paper discovery |
| | Semantic Scholar | Paper metadata |

---

## Learning Path

This project is designed to help you learn:

| Week | Focus | Activities |
|------|-------|------------|
| 1-2 | Understand | Run the system, explore API docs, read code |
| 3-4 | Modify | Edit configurations, adjust interests/courses |
| 5-6 | Extend | Add new features, customize quiz types |
| 7-8 | Build | Create new frontend components |
| Ongoing | Own | Full ownership - add whatever you want! |

See `docs/LEARNING_GUIDE.md` for detailed explanations.

---

## Troubleshooting

### Backend won't start

**Error:** `ImportError: attempted relative import with no known parent package`

**Solution:** Run from project root, not from inside `backend/`:
```bash
cd ~/daily-scholar           # ✅ Correct
uvicorn backend.main:app --reload

# NOT:
cd ~/daily-scholar/backend   # ❌ Wrong
uvicorn main:app --reload
```

### Frontend is slow to compile

**Cause:** Project is in a cloud-synced folder (OneDrive, Dropbox, iCloud)

**Solution:** Move project to a local directory:
```bash
cp -r /path/to/cloud/daily-scholar ~/daily-scholar
cd ~/daily-scholar/frontend
rm -rf node_modules .next
npm install
npm run dev
```

### CSS parsing error with @import

**Error:** `@import rules must precede all rules`

**Solution:** Move any `@import` statements to the very top of `frontend/app/globals.css`

### python command not found

**Solution:** Use `python3` instead:
```bash
python3 -m venv venv
python3 scripts/setup_db.py
```

### npm command not found

**Solution:** Install Node.js:
```bash
brew install node  # macOS with Homebrew
# Or download from https://nodejs.org/
```

### API returns null for papers

**Cause:** Network issues or no matching papers

**Solution:** 
1. Check your internet connection
2. Try `GET /papers/discover` directly in Swagger UI
3. Broaden your interests in `config/interests.yaml`

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is for personal educational use.
