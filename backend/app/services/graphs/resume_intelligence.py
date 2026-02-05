"""Graph 2 — Resume Intelligence + Shortlisting Graph.

Pipeline:
  1. Parse resume (PDF/DOC)
  2. Chunk text
  3. Embed → Chroma
  4. Semantic match vs JD
  5. Weighted scoring

Scoring Weights:
  Skills → 40%
  Projects → 30%
  Experience → 20%
  Tooling → 10%

NO keyword matching. Semantic only.
"""

from typing import TypedDict, List, Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.llm import get_llm
from app.services.vector_store.chroma_service import get_chroma_service
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Graph State ───────────────────────────────────────────────────

class ResumeGraphState(TypedDict):
    candidate_id: str
    jd_id: str
    resume_text: str
    jd_object: dict
    chunks: List[str]
    chunk_metadata: List[Dict[str, Any]]
    skills_score: float
    projects_score: float
    experience_score: float
    tooling_score: float
    final_score: float
    recommended: bool
    scoring_details: dict


# ── Node Functions ────────────────────────────────────────────────

async def parse_resume_node(state: ResumeGraphState) -> ResumeGraphState:
    """Extract structured information from resume text using LLM."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert resume parser. Extract structured information from the resume.
Return ONLY a JSON object with keys:
- "skills": list of technical skills
- "projects": list of project descriptions (brief)
- "experience_years": estimated years of experience (number)
- "tools": list of tools/frameworks/platforms
- "education": highest education level
- "summary": 2-3 sentence professional summary

Do not include any markdown formatting."""),
        ("human", "{resume_text}"),
    ])
    chain = prompt | llm
    response = await chain.ainvoke({"resume_text": state["resume_text"][:8000]})
    import json
    try:
        parsed = json.loads(response.content)
        state["chunk_metadata"] = [parsed]
    except (json.JSONDecodeError, AttributeError):
        state["chunk_metadata"] = [{"skills": [], "projects": [], "experience_years": 0}]
    logger.info(f"Resume parsed for candidate {state['candidate_id']}")
    return state


async def chunk_resume_node(state: ResumeGraphState) -> ResumeGraphState:
    """Chunk resume text for embedding."""
    text = state["resume_text"]
    chunk_size = 500
    overlap = 100
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        start += chunk_size - overlap

    state["chunks"] = chunks if chunks else [text]
    logger.info(f"Resume chunked: {len(state['chunks'])} chunks")
    return state


async def embed_resume_node(state: ResumeGraphState) -> ResumeGraphState:
    """Embed resume chunks into ChromaDB."""
    chroma = get_chroma_service()
    metadata = state.get("chunk_metadata", [{}])
    base_meta = metadata[0] if metadata else {}

    # Create per-chunk metadata
    chunk_metas = []
    for i, _ in enumerate(state["chunks"]):
        meta = {
            "candidate_id": state["candidate_id"],
            "chunk_index": i,
            "skills": str(base_meta.get("skills", [])),
            "experience_years": base_meta.get("experience_years", 0),
        }
        chunk_metas.append(meta)

    chroma.add_resume_chunks(
        candidate_id=state["candidate_id"],
        chunks=state["chunks"],
        metadata_list=chunk_metas,
    )
    logger.info(f"Resume embedded for candidate {state['candidate_id']}")
    return state


async def semantic_match_node(state: ResumeGraphState) -> ResumeGraphState:
    """Perform semantic matching between resume and JD across dimensions."""
    llm = get_llm()
    jd_obj = state["jd_object"]
    resume_meta = state["chunk_metadata"][0] if state.get("chunk_metadata") else {}
    resume_text_short = state["resume_text"][:4000]

    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert recruiter evaluating resume-JD fit.
Score the candidate on these dimensions (0.0 to 1.0):

1. skills_score: How well do the candidate's skills match the required skills?
   JD required skills: {must_have_skills}
   JD nice-to-have: {good_to_have}

2. projects_score: How relevant are the candidate's projects to the role?
   Role: {role}

3. experience_score: Does the experience level match?
   Required: {experience_range}

4. tooling_score: Does the candidate know the required tools?
   Required tools: {tools}

Use SEMANTIC understanding, not keyword matching.
Return ONLY a JSON: {{"skills_score": 0.0, "projects_score": 0.0, "experience_score": 0.0, "tooling_score": 0.0, "reasoning": "brief explanation"}}
Do not include any markdown formatting."""),
        ("human", "Resume:\n{resume_text}"),
    ])
    chain = prompt | llm
    response = await chain.ainvoke({
        "must_have_skills": str(jd_obj.get("must_have_skills", [])),
        "good_to_have": str(jd_obj.get("good_to_have", [])),
        "role": jd_obj.get("role", ""),
        "experience_range": jd_obj.get("experience_range", ""),
        "tools": str(jd_obj.get("tools", [])),
        "resume_text": resume_text_short,
    })

    import json
    try:
        scores = json.loads(response.content)
        state["skills_score"] = float(scores.get("skills_score", 0))
        state["projects_score"] = float(scores.get("projects_score", 0))
        state["experience_score"] = float(scores.get("experience_score", 0))
        state["tooling_score"] = float(scores.get("tooling_score", 0))
        state["scoring_details"] = scores
    except (json.JSONDecodeError, AttributeError, ValueError):
        state["skills_score"] = 0.0
        state["projects_score"] = 0.0
        state["experience_score"] = 0.0
        state["tooling_score"] = 0.0
        state["scoring_details"] = {}

    logger.info(f"Semantic match done for candidate {state['candidate_id']}")
    return state


async def weighted_scoring_node(state: ResumeGraphState) -> ResumeGraphState:
    """Compute final weighted score.

    Weights: Skills=40%, Projects=30%, Experience=20%, Tooling=10%
    """
    final = (
        state.get("skills_score", 0) * 0.40
        + state.get("projects_score", 0) * 0.30
        + state.get("experience_score", 0) * 0.20
        + state.get("tooling_score", 0) * 0.10
    )
    state["final_score"] = round(final, 4)
    from app.core.config import get_settings
    state["recommended"] = state["final_score"] >= get_settings().RESUME_SHORTLIST_THRESHOLD
    logger.info(
        f"Candidate {state['candidate_id']}: score={state['final_score']}, "
        f"recommended={state['recommended']}"
    )
    return state


# ── Build Graph ───────────────────────────────────────────────────

def build_resume_intelligence_graph() -> StateGraph:
    """Build and compile the Resume Intelligence Graph."""
    graph = StateGraph(ResumeGraphState)

    graph.add_node("parse_resume", parse_resume_node)
    graph.add_node("chunk_resume", chunk_resume_node)
    graph.add_node("embed_resume", embed_resume_node)
    graph.add_node("semantic_match", semantic_match_node)
    graph.add_node("weighted_scoring", weighted_scoring_node)

    graph.set_entry_point("parse_resume")
    graph.add_edge("parse_resume", "chunk_resume")
    graph.add_edge("chunk_resume", "embed_resume")
    graph.add_edge("embed_resume", "semantic_match")
    graph.add_edge("semantic_match", "weighted_scoring")
    graph.add_edge("weighted_scoring", END)

    return graph.compile()
