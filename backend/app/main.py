"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import init_db
from app.api.routes import jd_routes, candidate_routes, interview_routes, evaluation_routes
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    logger.info("Starting AI Interview Orchestrator...")
    await init_db()
    logger.info("Database initialized.")
    yield
    logger.info("Shutting down AI Interview Orchestrator...")


app = FastAPI(
    title="AI Interview Orchestrator",
    description="Agentic AI-powered interview platform with LangGraph orchestration",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(jd_routes.router)
app.include_router(candidate_routes.router)
app.include_router(interview_routes.router)
app.include_router(evaluation_routes.router)


@app.get("/")
async def root():
    return {
        "service": "AI Interview Orchestrator",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
