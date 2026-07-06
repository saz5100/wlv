# GCSE Computer Science — OCR J277 Revision Website

A full-featured revision website for GCSE Computer Science (OCR J277 / AQA 8525) with lessons, quizzes, exam-style questions, AI tutor, interactive code lab, and progress tracking.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    Docker Compose                     │
│  ┌──────────────┐          ┌──────────────────────┐  │
│  │  gcsecs-app  │◄────────►│     gcsecs-db        │  │
│  │  FastAPI      │  TCP     │  PostgreSQL 16        │  │
│  │  Uvicorn      │  5432    │  + pgvector           │  │
│  │  Port 8001    │          │  Volume: pgdata       │  │
│  └──────┬───────┘          └──────────────────────┘  │
│         │                                             │
│  Volume: activity-logs                                 │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Docker Desktop (Windows) or Docker Engine (Linux)
- Git
- API key for AI features (DeepSeek / Ollama Cloud)

### Setup

```bash
# 1. Clone the repo
git clone http://gitea.lan:3000/shazad/gcse-cs-website.git
cd gcse-cs-website

# 2. Configure environment
cp docker/.env.example .env
# Edit .env with your API keys

# 3. Start the stack
docker compose up -d

# 4. Open in browser
open http://localhost:8001
```

## Configuration

### Environment Variables (`.env`)

| Variable | Required | Default | Description |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | Yes | — | DeepSeek API key for AI marking |
| `OLLAMA_CLOUD_API_KEY` | Yes | — | Ollama Cloud API key (fallback) |
| `OLLAMA_CLOUD_BASE_URL` | No | `https://ollama.com/v1` | Ollama Cloud endpoint |
| `OLLAMA_CLOUD_MODEL` | No | `deepseek-v4-flash` | Model for AI features |

### Docker Compose (`docker-compose.yml`)

Two services:

- **`db`** — PostgreSQL 16 with pgvector extension. Data persisted in `pgdata` volume. Initialised via `init-db.sh` (creates `gcse_kb` database, installs pgvector, restores schema).
- **`app`** — FastAPI application served by Uvicorn (2 workers, port 8001). Depends on healthy DB. Activity logs stored in `activity-logs` volume.

### Database

PostgreSQL 16 with pgvector extension for semantic search.

**Connection details (internal):**
- Host: `db` (Docker DNS)
- Port: `5432`
- Database: `gcse_kb`
- User: `gcse_app`
- Password: `gcse_kb_2026`

**Backup:**
```bash
# Manual backup
docker exec gcsecs-db pg_dump -U gcse_app -d gcse_kb --clean --if-exists --no-owner > gcse_kb_dump.sql

# Restore
docker exec -i gcsecs-db psql -U gcse_app -d gcse_kb < gcse_kb_dump.sql
```

The `gcse_kb_dump.sql` file in the repo root is the latest production backup.

## Features

### Lessons
- 30+ topic lessons covering the full OCR J277 specification
- Interactive quizzes after each lesson
- Progress tracking with XP and mastery system

### Exam-Style Questions
- 6-mark and 8-mark written questions for every topic
- Timed mode (6 min for 6-mark, 10 min for 8-mark)
- AI-powered marking with detailed feedback
- Key terminology detection
- Model answers for comparison
- Links to AI Tutor for personalised help

### AI Tutor
- Conversational AI tutor for any GCSE CS topic
- Context-aware: links from exam results auto-populate the conversation
- Suggests topics based on weak areas
- Mermaid diagram rendering for visual explanations

### Code Lab
- In-browser Python execution via Pyodide (WebAssembly)
- Interactive coding exercises
- No server-side execution — runs entirely in the browser

### Quiz System
- Multiple-choice and short-answer questions
- Spaced repetition (SM-2 algorithm) for flashcards
- Topic-by-topic mastery tracking
- Working grade calculation

### Activity Dashboard
- Progress overview with grade summary
- Recent activity feed
- Weak area identification

## Deployment

### Windows (Docker Desktop)
```bash
docker compose up -d
```

### Linux (Docker Engine)
```bash
docker compose up -d
```

### Port Mapping
- `8001` — Application (FastAPI)
- `5432` — PostgreSQL (internal only)

### Health Check
```bash
curl http://localhost:8001/health
```

## Development

### Project Structure
```
gcse-cs-website/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── database.py           # Database connection helpers
│   ├── helpers.py            # Template rendering, user helpers
│   ├── routes/
│   │   ├── lessons.py        # Lesson content routes
│   │   ├── quiz.py           # Quiz and flashcard routes
│   │   ├── tutor.py          # AI Tutor routes
│   │   ├── misc.py           # Exam-style, grade, admin routes
│   │   ├── mark_my_paper.py  # Paper marking routes
│   │   └── activity.py       # Activity log routes
│   ├── templates/            # Jinja2 HTML templates
│   ├── static/               # CSS, JS, assets
│   └── requirements.txt      # Python dependencies
├── docker-compose.yml        # Docker Compose config
├── Dockerfile                # App container build
├── init-db.sh                # DB initialisation script
├── gcse_kb_dump.sql          # Production database backup
├── gcse_kb_fresh.sql         # Fresh schema (no data)
├── backup_gcsecs.sh          # Legacy SQLite backup script
└── .env                      # Environment variables (gitignored)
```

### Adding a New Topic
1. Add topic to `topics` table in the database
2. Create lesson content in `lessons` table
3. Add quiz questions to `quiz_questions` table
4. Add exam-style questions to `exam_questions` table

## Version History

| Tag | Date | Description |
|---|---|---|
| v2.33.76 | 2026-07-01 | Exam-style fixes: key terms, AI Tutor links, timer spacing |
| v1.8 | 2026-07-01 | Docker migration, PostgreSQL, pgvector |
| v1.4 | 2026-06-30 | AI Tutor streaming, Mermaid diagrams |
| v1.0 | 2026-06-28 | Initial release |

## License

Private — GCSE Computer Science revision platform for personal/educational use.
