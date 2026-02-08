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
    vector_score: float
    final_score: float
    recommended: bool
    scoring_details: dict
    threshold: Optional[float]


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
        ("system", """You are an expert technical recruiter. Evaluate the candidate's fit for the specific Job Description (JD) requirements.

CRITICAL INSTRUCTIONS:
1. CALCULATE EXPERIENCE: Estimate the candidate's total years of RELEVANT full-time experience. Ignore internships unless the JD allows them.
2. COMPARE WITH REQUIRED: {experience_range}.
3. PENALIZE MISMATCH: 
   - If the candidate has FEWER years than the minimum required, 'experience_score' MUST be 0.0.
   - If the candidate is a student/undergraduate and the role requires experience, 'experience_score' MUST be 0.0.
   - Do not hallucinate experience.

Score dimensions (0.0 to 1.0):
1. skills_score: Semantic match of technical skills. Priorities: {must_have_skills}.
2. projects_score: Relevance and complexity of projects given the role ({role}).
3. experience_score: Strict adherence to years of experience. 0.0 if not met.
4. tooling_score: Proficiency in required tools ({tools}).

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

    New Weights (Project Priority):
      Projects: 40%
      Skills: 30%
      Vector Match: 15%
      Experience: 10%
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
