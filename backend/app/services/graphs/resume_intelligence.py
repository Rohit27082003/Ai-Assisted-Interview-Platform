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
from datetime import datetime
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.llm import get_llm, get_structured_llm
from app.services.vector_store.chroma_service import get_chroma_service
from app.core.logging import get_logger
from app.prompts.resume_prompts import RESUME_PARSER_PROMPT, RESUME_ANALYSIS_PROMPT
from app.schemas.outputs.resume_outputs import ResumeData, ScoringDetails

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
    vector_score: float
    final_score: float
    recommended: bool
    scoring_details: dict
    threshold: Optional[float]


# ── Node Functions ────────────────────────────────────────────────

async def parse_resume_node(state: ResumeGraphState) -> ResumeGraphState:
    """Extract structured information from resume text using LLM."""
    # Use structured LLM for strict schema validation
    llm = get_structured_llm(ResumeData)
    prompt = RESUME_PARSER_PROMPT
    chain = prompt | llm

    # Get current date for accurate date interpretation
    current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "February 10, 2026"

    try:
        parsed_data: ResumeData = await chain.ainvoke({
            "resume_text": state["resume_text"][:8000],
            "current_date": current_date
        })
        # Convert Pydantic model to dict for state storage
        state["chunk_metadata"] = [parsed_data.model_dump()]
        logger.info(f"Resume parsed successfully for {state['candidate_id']}")
    except Exception as e:
        logger.error(f"Failed to parse resume JSON for {state['candidate_id']}: {e}")
        state["chunk_metadata"] = [{"skills": [], "projects": [], "experience_years": 0}]

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
    jd_obj = state["jd_object"]
    resume_text_short = state["resume_text"][:6000] # Increased context window

    # Use structured LLM for strict schema validation
    llm = get_structured_llm(ScoringDetails)
    prompt = RESUME_ANALYSIS_PROMPT
    chain = prompt | llm
    
    try:
        scores: ScoringDetails = await chain.ainvoke({
            "must_have_skills": str(jd_obj.get("must_have_skills", [])),
            "good_to_have": str(jd_obj.get("good_to_have", [])),
            "role": jd_obj.get("role", ""),
            "experience_range": jd_obj.get("experience_range", ""),
            "tools": str(jd_obj.get("tools", [])),
            "resume_text": resume_text_short,
            "current_date": datetime.now().strftime("%B %d, %Y"),
        })

        # Normalize 0-100 scale to 0.0-1.0
        state["skills_score"] = float(scores.skills_score) / 100.0
        state["projects_score"] = float(scores.projects_score) / 100.0
        state["experience_score"] = float(scores.experience_score) / 100.0
        state["tooling_score"] = float(scores.tooling_score) / 100.0
        
        # Keep detailed reasoning (dump model to dict)
        state["scoring_details"] = scores.model_dump()
        
        logger.info(f"Semantic match: {scores.overall_match_confidence}% confidence")
    except Exception as e:
        logger.error(f"Failed to parse semantic match scores: {e}")
        state["skills_score"] = 0.0
        state["projects_score"] = 0.0
        state["experience_score"] = 0.0
        state["tooling_score"] = 0.0
        state["scoring_details"] = {
            "reasoning": "Failed to parse AI analysis. Please try again.",
            "pros": [], 
            "cons": [], 
            "red_flags": []
        }

    return state


async def vector_scoring_node(state: ResumeGraphState) -> ResumeGraphState:
    """Compute vector similarity score between Resume and JD using ChromaDB."""
    chroma = get_chroma_service()
    
    # Ensure vectors are computed/available
    # Assuming embed_resume_node already added them to Chroma
    
    similarity = chroma.compute_similarity_score(
        resume_candidate_id=state["candidate_id"],
        jd_id=state["jd_id"],
    )
    
    state["vector_score"] = similarity
    logger.info(f"Vector score for candidate {state['candidate_id']}: {similarity:.4f}")
    return state


async def weighted_scoring_node(state: ResumeGraphState) -> ResumeGraphState:
    """Compute final weighted score.

    Weights (Stricter Experience Control):
      Projects: 30%
      Skills: 25%
      Experience: 25%
      Vector Match: 15%
      Tooling: 5%
    """
    skills = state.get("skills_score", 0)
    projects = state.get("projects_score", 0)
    experience = state.get("experience_score", 0)
    tooling = state.get("tooling_score", 0)
    vector = state.get("vector_score", 0)

    # Adjusted Weights for stricter experience control
    # Experience: 25%, Projects: 30%, Skills: 25%, Vector: 15%, Tooling: 5%
    final = (
        (projects * 0.30) +
        (skills * 0.25) +
        (vector * 0.15) +
        (experience * 0.25) +
        (tooling * 0.05)
    )

    # KNOCKOUT RULE: If experience score is too low (meaning requirements not met), 
    # cap the final score to ensure rejection.
    if experience < 0.3:  # 0.3 allows for some margin but rejects clear mismatches (0.0)
        logger.info(f"Candidate {state['candidate_id']} rejected due to low experience score ({experience})")
        final = min(final, 0.4)  # Cap below typical threshold (0.7)
    
    state["final_score"] = round(final, 4)
    
    # Update scoring details for dashboard
    details = state.get("scoring_details", {})
    details.update({
        "vector_score": round(vector, 4),
        "final_score": round(final, 4),
        # Ensure we have consistent keys for frontend
        "skills_score": round(skills, 4),
        "projects_score": round(projects, 4),
        "experience_score": round(experience, 4),
        "tooling_score": round(tooling, 4),
    })
    state["scoring_details"] = details

    from app.core.config import get_settings
    # Use dynamic threshold if provided in state, else fallback to settings
    threshold = state.get("threshold")
    if threshold is None:
        threshold = get_settings().RESUME_SHORTLIST_THRESHOLD

    state["recommended"] = state["final_score"] >= threshold
    logger.info(
        f"Candidate {state['candidate_id']}: score={state['final_score']}, "
        f"recommended={state['recommended']} (threshold={threshold})"
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
    graph.add_node("vector_scoring", vector_scoring_node)
    graph.add_node("weighted_scoring", weighted_scoring_node)

    graph.set_entry_point("parse_resume")
    graph.add_edge("parse_resume", "chunk_resume")
    graph.add_edge("chunk_resume", "embed_resume")
    graph.add_edge("embed_resume", "semantic_match")
    graph.add_edge("semantic_match", "vector_scoring")
    graph.add_edge("vector_scoring", "weighted_scoring")
    graph.add_edge("weighted_scoring", END)

    return graph.compile()
