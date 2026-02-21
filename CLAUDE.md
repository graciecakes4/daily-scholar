# CLAUDE.md

## Project Overview
Daily Scholar is a personalized learning system for academic research and knowledge acquisition.
It discovers research papers (arXiv, CORE API, Semantic Scholar), generates topic reviews,
creates quizzes, and tracks learning progress.

## Architecture
- Backend: FastAPI + SQLAlchemy (Python)
- Frontend: Next.js (App Router)
- Database: SQLite
- File uploads stored in uploads/ with UUID-based filenames

## Code Standards

### General
- use snake_case for python, camelCase for javascript/typescript
- keep functions short and single-purpose
- prefer vectorized operations over explicit loops in python (numpy, pandas)
- no unused imports or dead code

### Comments
- all comments must be lowercase only
- comments go on the line above the code, never inline
- correct: `# filter active users` on its own line above the code
- incorrect: `df = filter(df) # Filter active users`

### R Code
- always use package::function() notation (e.g., dplyr::filter(), readr::read_csv())
- only base R functions (c, list, print, paste, data.frame, etc.) are exempt

### Python / FastAPI
- always use proper session management with cleanup in database operations
- use pydantic models for request/response validation
- handle errors explicitly, no bare except clauses
- use async endpoints where appropriate

### Frontend / Next.js
- use app router conventions
- use FormData for file uploads
- handle loading and error states in all pages
- keep components modular

### Database
- use prefixed unique identifiers for deduplication (arxiv:, doi:, hash:)
- always clean up database sessions in finally blocks
- use alembic-style migrations for schema changes

## File Structure
- backend/ - FastAPI application
- frontend/ - Next.js application
- uploads/course_materials/ - organized by course with lectures/, notes/, textbooks/ subdirectories

## README
- any changes to features, APIs, dependencies, or usage patterns must include
  corresponding README updates