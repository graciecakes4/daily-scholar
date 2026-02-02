# Daily Scholar - Learning Guide 📚

This document explains how each component works and provides guidance for understanding and modifying the codebase as you learn.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Backend Deep Dive](#backend-deep-dive)
3. [Frontend Deep Dive](#frontend-deep-dive)
4. [Learning Path](#learning-path)
5. [Common Tasks](#common-tasks)
6. [Troubleshooting](#troubleshooting)

---

## Architecture Overview

### The Big Picture

Daily Scholar follows a classic **client-server architecture**:

```
┌─────────────────┐         ┌─────────────────┐         ┌─────────────────┐
│                 │  HTTP   │                 │  Calls  │                 │
│    Frontend     │◄───────►│    Backend      │◄───────►│  External APIs  │
│   (Next.js)     │  JSON   │   (FastAPI)     │         │ (arXiv, Claude) │
│                 │         │                 │         │                 │
└─────────────────┘         └─────────────────┘         └─────────────────┘
                                    │
                                    │ Reads/Writes
                                    ▼
                            ┌─────────────────┐
                            │    Database     │
                            │    (SQLite)     │
                            └─────────────────┘
```

### Why These Technologies?

| Technology | Why We Use It |
|------------|---------------|
| **FastAPI** | Modern Python web framework. Auto-generates docs, type-safe, async support. |
| **SQLite** | Simple file-based database. No server needed, easy to backup. |
| **Next.js** | React framework with routing, SSR, and great developer experience. |
| **Pydantic** | Data validation in Python. Catches errors early, auto-documents API. |
| **Claude API** | AI for content generation. Produces summaries, quizzes, reviews. |

---

## Backend Deep Dive

### File Structure Explained

```
backend/
├── main.py              # Application entry point
├── config.py            # Configuration management
├── database.py          # Database models and setup
├── models.py            # API request/response schemas
└── services/
    ├── paper_discovery.py    # Finding papers
    └── content_generator.py  # AI content creation
```

### Key Concepts

#### 1. FastAPI Endpoints

An **endpoint** is a URL that accepts requests and returns responses:

```python
@app.get("/papers/discover")           # Decorator defines the URL and method
async def discover_papers(             # Function that handles the request
    max_results: int = 10,             # Query parameter with default
):
    # Business logic here
    return {"papers": [...]}           # Response (auto-converted to JSON)
```

**Try it:** Visit `http://localhost:8000/docs` to see all endpoints and test them interactively.

#### 2. Dependency Injection

FastAPI lets you "inject" common dependencies into endpoints:

```python
# Instead of creating a database session in every endpoint:
async def get_items():
    session = create_session()  # ❌ Repetitive
    ...

# You can inject it:
async def get_items(db: Session = Depends(get_db)):  # ✅ Clean
    ...
```

#### 3. Async/Await

Python `async` functions can pause while waiting for I/O (like API calls):

```python
# Without async - blocks while waiting
def get_paper():
    response = requests.get(url)  # Blocks everything
    return response.json()

# With async - other things can run while waiting
async def get_paper():
    response = await client.get(url)  # Other tasks can run
    return response.json()
```

#### 4. Services Pattern

We separate **business logic** into services:

```
main.py          →  Defines API endpoints (what URLs exist)
services/*.py    →  Contains business logic (what actually happens)
```

This separation makes code easier to test and maintain.

### Configuration System

Configuration comes from two places:

1. **Environment Variables** (`.env`) - Secrets and deployment settings
   ```
   ANTHROPIC_API_KEY=sk-...
   DATABASE_URL=sqlite:///...
   ```

2. **YAML Files** (`config/`) - User-editable content
   ```yaml
   interests:
     primary:
       - name: "Machine Learning"
         keywords: ["deep learning", "neural networks"]
   ```

**Why split?** Secrets should never be in version control. YAML is easier to edit for non-secrets.

---

## Frontend Deep Dive

### File Structure Explained

```
frontend/
├── app/                 # Next.js App Router pages
│   ├── page.tsx        # Home page (/)
│   ├── daily/page.tsx  # Daily content (/daily)
│   └── layout.tsx      # Shared layout
├── components/          # Reusable UI components
│   ├── PaperCard.tsx
│   ├── QuizQuestion.tsx
│   └── TopicReview.tsx
├── lib/                 # Utility functions
│   └── api.ts          # API client functions
└── types/              # TypeScript type definitions
```

### Key Concepts

#### 1. React Components

Components are reusable UI pieces:

```tsx
// A simple component
function PaperCard({ title, authors }) {
  return (
    <div className="card">
      <h2>{title}</h2>
      <p>By: {authors.join(", ")}</p>
    </div>
  );
}

// Using the component
<PaperCard title="Paper Title" authors={["Alice", "Bob"]} />
```

#### 2. State Management

React tracks changes with **state**:

```tsx
function Quiz() {
  // useState creates a variable that triggers re-render when changed
  const [score, setScore] = useState(0);
  const [currentQuestion, setCurrentQuestion] = useState(0);
  
  function handleCorrect() {
    setScore(score + 1);  // This triggers re-render
    setCurrentQuestion(currentQuestion + 1);
  }
  
  return <div>Score: {score}</div>;
}
```

#### 3. API Calls with Fetch

To get data from the backend:

```tsx
async function loadPapers() {
  const response = await fetch("http://localhost:8000/papers/discover");
  const data = await response.json();
  return data.papers;
}
```

#### 4. Tailwind CSS

Tailwind uses utility classes instead of custom CSS:

```tsx
// Traditional CSS
<div className="paper-card">  // Then define .paper-card in CSS file

// Tailwind
<div className="bg-white rounded-lg shadow p-4">  // Styles right in HTML
```

---

## Learning Path

### Week 1-2: Understanding the System

**Goal:** Be able to run the system and understand how parts connect.

**Tasks:**
1. [ ] Run the backend: `cd backend && uvicorn main:app --reload`
2. [ ] Explore the API docs at `http://localhost:8000/docs`
3. [ ] Try each endpoint manually
4. [ ] Read through `main.py` and follow the code flow
5. [ ] Modify `config/interests.yaml` and see how it affects paper discovery

**Checkpoints:**
- Can you explain what happens when you call `/daily`?
- Can you find where quiz questions are generated?

### Week 3-4: Making Small Changes

**Goal:** Modify existing functionality confidently.

**Tasks:**
1. [ ] Add a new interest category to `interests.yaml`
2. [ ] Change the number of quiz questions generated
3. [ ] Modify the paper relevance scoring algorithm
4. [ ] Add a new field to the topic configuration

**Checkpoints:**
- Can you add a new course topic and generate a review for it?
- Can you adjust the difficulty of quizzes?

### Week 5-6: Adding New Features (Backend)

**Goal:** Add new endpoints and services.

**Project Ideas:**
1. [ ] Add a "bookmark paper" endpoint
2. [ ] Create a progress tracking endpoint
3. [ ] Add paper filtering by date range
4. [ ] Implement the spaced repetition algorithm

**Skills You'll Practice:**
- Creating new endpoints
- Writing service functions
- Database queries

### Week 7-8: Adding New Features (Frontend)

**Goal:** Build new UI components.

**Project Ideas:**
1. [ ] Build a progress dashboard
2. [ ] Add a paper bookmarks page
3. [ ] Create a topic mastery visualization
4. [ ] Add dark mode support

**Skills You'll Practice:**
- React components
- State management
- API integration

### Ongoing: Full Ownership

At this point, you should be able to:
- Add any feature you want
- Debug issues independently
- Refactor code for better organization
- Deploy the application

---

## Common Tasks

### Adding a New API Endpoint

1. **Define the endpoint in `main.py`:**
   ```python
   @app.get("/my-new-endpoint")
   async def my_new_function(param: str):
       # Your logic here
       return {"result": "value"}
   ```

2. **Add response model in `models.py`** (optional but recommended):
   ```python
   class MyResponse(BaseModel):
       result: str
   ```

3. **Test in the docs:** Visit `/docs` and try it out.

### Adding a New Paper Source

1. **Open `services/paper_discovery.py`**

2. **Add a new search method:**
   ```python
   async def search_new_source(self, query: str) -> list[Paper]:
       # Call the API
       # Parse the response
       # Return list of Paper objects
   ```

3. **Include it in `discover_papers()`:**
   ```python
   if "new_source" in sources:
       tasks.append(self.search_new_source(term))
   ```

### Changing Quiz Question Types

1. **Open `services/content_generator.py`**

2. **Modify the prompt in `generate_quiz_questions()`**

3. **Add new type descriptions to the prompt**

4. **Update `models.py` if needed for new response fields**

### Adding a Database Table

1. **Define the model in `database.py`:**
   ```python
   class MyNewTable(Base):
       __tablename__ = "my_new_table"
       id = Column(Integer, primary_key=True)
       # ... other columns
   ```

2. **Run the setup script to create the table**

3. **Use it in your endpoints**

---

## Troubleshooting

### "Module not found" errors

```bash
# Make sure you're in the right directory and venv is activated
cd daily-scholar
source venv/bin/activate
pip install -r requirements.txt
```

### API key errors

```bash
# Check your .env file has valid keys
cat .env | grep API_KEY
```

### CORS errors in browser

The frontend URL must be in the allowed origins. Check `main.py`:
```python
allow_origins=[
    "http://localhost:3000",  # Add your frontend URL
]
```

### Database errors

```bash
# Delete and recreate the database
rm data/daily_scholar.db
python scripts/setup_db.py
```

### Paper discovery returns nothing

1. Check your internet connection
2. Try broader keywords in `interests.yaml`
3. Increase `days_back` parameter
4. Check arXiv/Semantic Scholar aren't rate limiting

---

## Resources for Learning More

### Python & FastAPI
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Real Python Tutorials](https://realpython.com/)
- [Python Async IO Tutorial](https://realpython.com/async-io-python/)

### React & Next.js
- [React Documentation](https://react.dev/)
- [Next.js Documentation](https://nextjs.org/docs)
- [Tailwind CSS Documentation](https://tailwindcss.com/docs)

### APIs & Data
- [arXiv API Documentation](https://arxiv.org/help/api/)
- [Semantic Scholar API](https://api.semanticscholar.org/)
- [Anthropic Claude API](https://docs.anthropic.com/)

---

## Questions?

As you work through this codebase, keep notes of:
1. Things that confuse you
2. Ideas for improvements
3. Bugs you encounter

These become great learning opportunities and potential contributions!
