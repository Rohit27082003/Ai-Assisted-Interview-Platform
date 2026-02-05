# AI Interview Orchestrator

An Agentic AI-powered interview platform that autonomously manages the entire interview pipeline — from job description parsing to candidate evaluation and recruiter report generation.

## Architecture

The system is built as a **state machine**, not a chatbot. Every operation is graph-orchestrated using LangGraph with persistent state in PostgreSQL.

### Pipeline Flow

```
JD Intelligence → Resume Intelligence → Shortlisting → Focus Areas → Interview → Evaluation → Report
```

### Core Stack

| Component | Technology |
|-----------|-----------|
| Agent Orchestration | LangGraph |
| LLM Tools & Prompting | LangChain + Groq (Llama 3.3 70B) |
| Real-time Transcription | AWS Transcribe Streaming |
| File Storage | Amazon S3 |
| Primary Database | PostgreSQL (with JSONB state) |
| Vector Store | ChromaDB |
| API Gateway | FastAPI |
| Live Streaming | WebSocket |
| Frontend | React + TypeScript + Tailwind CSS |

### Graph Architecture

```
Master Orchestrator (Router)
├── Graph 1: JD Intelligence
│   ├── JD Parser
│   ├── Skill Extractor
│   ├── Competency Mapper
│   └── Mandatory/Preferred Classifier
├── Graph 2: Resume Intelligence
│   ├── Resume Parser (PDF/DOC)
│   ├── Chunker
│   ├── Vector Embedder (ChromaDB)
│   ├── Semantic Matcher (vs JD)
│   └── Weighted Scorer (Skills 40%, Projects 30%, Experience 20%, Tooling 10%)
├── Graph 3: Focus Area Selection
│   ├── Overlap Analyzer
│   └── Focus Validator (4-5 areas)
├── Graph 4: Interview Orchestration (Event-Driven)
│   ├── Pillar Selector
│   ├── Question Generator
│   ├── Answer Understanding
│   ├── Follow-up Generator
│   └── Pillar Shifter
├── Graph 5: Evaluation
│   ├── Reference Answer Generator
│   ├── Rubric Scorer (1-5 on correctness, depth, reasoning, clarity)
│   └── Score Aggregator
└── Graph 6: Reporting
    ├── Performance Analyzer
    ├── Recommendation Generator
    └── Report Compiler
```

### Cheating Detection Agent

Runs in parallel during interviews:
- **Semantic similarity check**: Detects question parroting (`similarity > 0.8`)
- **Novel token ratio**: Flags low-novelty answers
- **LLM-based analysis**: Catches scripted/copied responses
- **Escalation**: `warning_1 → warning_2 → penalty`

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/routes/           # FastAPI route handlers
│   │   ├── core/                 # Config, database, LLM setup
│   │   ├── models/               # SQLAlchemy ORM models
│   │   ├── schemas/              # Pydantic schemas
│   │   └── services/
│   │       ├── graphs/           # LangGraph workflows
│   │       ├── agents/           # Cheating detection
│   │       ├── aws/              # S3, Transcribe services
│   │       └── vector_store/     # ChromaDB service
│   ├── schema.sql                # PostgreSQL DDL
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── components/           # React UI components
│       ├── pages/                # Page views
│       ├── services/             # API client
│       ├── store/                # Zustand state
│       └── types/                # TypeScript types
├── docker-compose.yml
└── .env
```

## Setup

### Prerequisites

- Docker & Docker Compose
- Python 3.11+
- Node.js 20+
- PostgreSQL 16+

### Quick Start (Docker)

```bash
# Clone and start all services
docker-compose up -d

# Access:
# Frontend: http://localhost:5173
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Manual Setup

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Initialize database
psql -U postgres -f schema.sql

# Start server
uvicorn app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/jd/` | Create & parse job description |
| GET | `/api/jd/` | List job descriptions |
| POST | `/api/candidates/` | Register candidate |
| POST | `/api/candidates/{id}/upload-resume` | Upload resume |
| POST | `/api/candidates/{jd_id}/shortlist` | Run AI shortlisting |
| POST | `/api/candidates/{id}/focus-areas` | Generate focus areas |
| POST | `/api/interviews/start` | Start interview session |
| WS | `/api/interviews/ws/{id}` | Live interview WebSocket |
| POST | `/api/evaluations/{id}/evaluate` | Run evaluation |
| POST | `/api/evaluations/{id}/report` | Generate report |
| GET | `/api/evaluations/{id}/report` | Get report |

## Database Schema

- **job_descriptions**: Parsed JDs with skills, tools, competencies
- **candidates**: Resume data, shortlist scores, focus areas, graph state
- **interviews**: Session state (JSONB), pillar tracking, cheating level
- **transcripts**: Per-question records with audio URLs, cheating flags
- **evaluations**: Rubric scores (correctness, depth, reasoning, clarity)
- **reports**: Final recommendation, strengths, weaknesses, confidence score

## Environment Variables

See `.env` file for all configuration options including Groq API keys, AWS credentials, database URLs, and interview timing parameters.
