"""
Enhanced ChromaDB Service for Semantic Resume Shortlisting

This module provides production-grade vector search capabilities for:
- Resume to JD semantic matching
- Multi-dimensional skill matching
- Contextual project relevance scoring
- Interview answer similarity checking

Key Features:
- Chunked embeddings with rich metadata
- Cross-collection semantic comparison
- Batch processing for multiple candidates
- Caching for repeated queries
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter

from app.core.logging import get_logger
from app.core.config import get_settings

logger = get_logger(__name__)
settings = get_settings()


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SemanticMatchConfig:
    """Configuration for semantic matching."""
    # Chunk settings
    chunk_size: int = 512
    chunk_overlap: int = 50

    # Search settings
    top_k_per_query: int = 5
    similarity_threshold: float = 0.3  # Minimum similarity to consider

    # Scoring weights (must sum to 1.0)
    skills_weight: float = 0.40
    projects_weight: float = 0.30
    experience_weight: float = 0.20
    tools_weight: float = 0.10

    # Model settings
    embedding_model: str = "all-MiniLM-L6-v2"


DEFAULT_CONFIG = SemanticMatchConfig()


# ═══════════════════════════════════════════════════════════════════════════════
# SEMANTIC MATCH RESULT
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class SemanticMatchResult:
    """Result of semantic matching between resume and JD."""
    candidate_id: str
    jd_id: str

    # Dimension scores (0-1)
    skills_score: float
    projects_score: float
    experience_score: float
    tools_score: float

    # Computed final score
    final_score: float
    recommended: bool

    # Details for explainability
    matched_skills: List[Tuple[str, float]]  # (skill, similarity)
    matched_projects: List[Tuple[str, float]]
    top_matches: List[Dict[str, Any]]  # Top matching chunks
    reasoning: str


# ═══════════════════════════════════════════════════════════════════════════════
# ENHANCED CHROMA SERVICE
# ═══════════════════════════════════════════════════════════════════════════════


class EnhancedChromaService:
    """
    Production-grade ChromaDB service for semantic resume matching.

    Features:
    - Multi-collection management (resumes, JDs, skills)
    - Semantic similarity scoring across dimensions
    - Batch candidate evaluation
    - Query caching for performance
    """

    RESUMES_COLLECTION = "resumes_v2"
    JD_COLLECTION = "job_descriptions_v2"
    SKILLS_COLLECTION = "skills_embeddings"

    def __init__(self, config: Optional[SemanticMatchConfig] = None):
        """Initialize the enhanced ChromaDB service."""
        self.config = config or DEFAULT_CONFIG

        # Initialize embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name=self.config.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},  # Important for cosine
        )

        # Initialize text splitter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

        # Initialize vector stores with persistence
        persist_dir = settings.CHROMA_PERSIST_DIR if hasattr(settings, 'CHROMA_PERSIST_DIR') else None

        self.resumes_db = Chroma(
            collection_name=self.RESUMES_COLLECTION,
            embedding_function=self.embeddings,
            persist_directory=persist_dir,
            collection_metadata={"hnsw:space": "cosine"},
        )

        self.jd_db = Chroma(
            collection_name=self.JD_COLLECTION,
            embedding_function=self.embeddings,
            persist_directory=persist_dir,
            collection_metadata={"hnsw:space": "cosine"},
        )

        # Cache for embeddings
        self._embedding_cache: Dict[str, np.ndarray] = {}

        logger.info("Enhanced ChromaDB service initialized")

    # ─── Resume Indexing ──────────────────────────────────────────────────────

    async def index_resume(
        self,
        candidate_id: str,
        resume_text: str,
        parsed_data: Dict[str, Any],
    ) -> List[str]:
        """
        Index a resume with rich metadata for semantic search.

        Args:
            candidate_id: Unique candidate identifier
            resume_text: Full resume text
            parsed_data: Parsed resume structure (skills, projects, etc.)

        Returns:
            List of chunk IDs
        """
        # Create chunks
        chunks = self.text_splitter.split_text(resume_text)

        if not chunks:
            chunks = [resume_text[:self.config.chunk_size]]

        # Create metadata for each chunk
        skills = parsed_data.get("skills", [])
        projects = parsed_data.get("projects", [])
        experience = parsed_data.get("experience_years", 0)
        tools = parsed_data.get("tools", [])

        chunk_ids = []
        texts = []
        metadatas = []

        for i, chunk in enumerate(chunks):
            chunk_id = f"{candidate_id}_chunk_{i}"

            # Determine chunk type based on content
            chunk_lower = chunk.lower()
            chunk_type = "general"
            if any(word in chunk_lower for word in ["project", "built", "developed", "implemented"]):
                chunk_type = "project"
            elif any(word in chunk_lower for word in ["skill", "proficient", "experience", "knowledge"]):
                chunk_type = "skills"
            elif any(word in chunk_lower for word in ["education", "degree", "university", "college"]):
                chunk_type = "education"
            elif any(word in chunk_lower for word in ["work", "company", "position", "role"]):
                chunk_type = "experience"

            metadata = {
                "candidate_id": candidate_id,
                "chunk_index": i,
                "chunk_type": chunk_type,
                "skills": ", ".join(skills[:10]) if skills else "",
                "experience_years": experience,
                "has_tools": bool(tools),
                "chunk_length": len(chunk),
            }

            chunk_ids.append(chunk_id)
            texts.append(chunk)
            metadatas.append(metadata)

        # Add to collection
        self.resumes_db.add_texts(
            texts=texts,
            metadatas=metadatas,
            ids=chunk_ids,
        )

        logger.info(f"Indexed {len(chunks)} chunks for candidate {candidate_id}")
        return chunk_ids

    # ─── JD Indexing ──────────────────────────────────────────────────────────

    async def index_jd(
        self,
        jd_id: str,
        jd_text: str,
        parsed_jd: Dict[str, Any],
    ) -> List[str]:
        """
        Index a job description for semantic matching.

        Args:
            jd_id: Unique JD identifier
            jd_text: Full JD text
            parsed_jd: Parsed JD structure (skills, requirements, etc.)

        Returns:
            List of chunk IDs
        """
        # Create semantic chunks for different aspects
        chunks_data = []

        # Skills chunk
        must_have = parsed_jd.get("must_have_skills", [])
        good_to_have = parsed_jd.get("good_to_have", [])
        if must_have or good_to_have:
            skills_text = f"Required skills: {', '.join(must_have)}. Nice to have: {', '.join(good_to_have)}"
            chunks_data.append({
                "text": skills_text,
                "type": "skills",
                "importance": "high",
            })

        # Tools chunk
        tools = parsed_jd.get("tools", [])
        if tools:
            tools_text = f"Required tools and technologies: {', '.join(tools)}"
            chunks_data.append({
                "text": tools_text,
                "type": "tools",
                "importance": "medium",
            })

        # Experience chunk
        exp_range = parsed_jd.get("experience_range", "")
        if exp_range:
            exp_text = f"Required experience: {exp_range}"
            chunks_data.append({
                "text": exp_text,
                "type": "experience",
                "importance": "high",
            })

        # Role description chunk
        role = parsed_jd.get("role", "")
        competencies = parsed_jd.get("competencies", [])
        if role or competencies:
            role_text = f"Role: {role}. Key competencies: {', '.join(competencies)}"
            chunks_data.append({
                "text": role_text,
                "type": "role",
                "importance": "high",
            })

        # Full text chunks
        text_chunks = self.text_splitter.split_text(jd_text)
        for i, chunk in enumerate(text_chunks):
            chunks_data.append({
                "text": chunk,
                "type": "full_text",
                "importance": "medium",
            })

        # Add to collection
        chunk_ids = []
        texts = []
        metadatas = []

        for i, chunk_info in enumerate(chunks_data):
            chunk_id = f"{jd_id}_chunk_{i}"
            metadata = {
                "jd_id": jd_id,
                "chunk_index": i,
                "chunk_type": chunk_info["type"],
                "importance": chunk_info["importance"],
            }

            chunk_ids.append(chunk_id)
            texts.append(chunk_info["text"])
            metadatas.append(metadata)

        self.jd_db.add_texts(
            texts=texts,
            metadatas=metadatas,
            ids=chunk_ids,
        )

        logger.info(f"Indexed {len(chunks_data)} chunks for JD {jd_id}")
        return chunk_ids

    # ─── Semantic Matching ────────────────────────────────────────────────────

    async def compute_semantic_match(
        self,
        candidate_id: str,
        jd_id: str,
        parsed_resume: Dict[str, Any],
        parsed_jd: Dict[str, Any],
    ) -> SemanticMatchResult:
        """
        Compute semantic similarity between a candidate and JD.

        Uses vector similarity across multiple dimensions:
        - Skills matching
        - Project relevance
        - Experience fit
        - Tools alignment

        Args:
            candidate_id: Candidate identifier
            jd_id: JD identifier
            parsed_resume: Parsed resume data
            parsed_jd: Parsed JD data

        Returns:
            SemanticMatchResult with scores and details
        """
        logger.info(f"Computing semantic match: candidate={candidate_id}, jd={jd_id}")

        # Run dimension scores in parallel
        skills_task = self._compute_skills_score(candidate_id, parsed_resume, parsed_jd)
        projects_task = self._compute_projects_score(candidate_id, parsed_resume, parsed_jd)
        experience_task = self._compute_experience_score(parsed_resume, parsed_jd)
        tools_task = self._compute_tools_score(candidate_id, parsed_resume, parsed_jd)

        skills_result, projects_result, experience_score, tools_result = await asyncio.gather(
            skills_task, projects_task, experience_task, tools_task
        )

        skills_score, matched_skills = skills_result
        projects_score, matched_projects = projects_result
        tools_score, _ = tools_result

        # Get top matching resume chunks against JD
        top_matches = await self._get_top_matches(candidate_id, jd_id)

        # Compute weighted final score
        final_score = (
            skills_score * self.config.skills_weight
            + projects_score * self.config.projects_weight
            + experience_score * self.config.experience_weight
            + tools_score * self.config.tools_weight
        )

        # Determine recommendation
        threshold = settings.RESUME_SHORTLIST_THRESHOLD
        recommended = final_score >= threshold

        # Generate reasoning
        reasoning = self._generate_reasoning(
            skills_score, projects_score, experience_score, tools_score,
            matched_skills, final_score, threshold
        )

        result = SemanticMatchResult(
            candidate_id=candidate_id,
            jd_id=jd_id,
            skills_score=round(skills_score, 4),
            projects_score=round(projects_score, 4),
            experience_score=round(experience_score, 4),
            tools_score=round(tools_score, 4),
            final_score=round(final_score, 4),
            recommended=recommended,
            matched_skills=matched_skills[:5],
            matched_projects=matched_projects[:3],
            top_matches=top_matches,
            reasoning=reasoning,
        )

        logger.info(
            f"Semantic match result: candidate={candidate_id}, "
            f"score={final_score:.3f}, recommended={recommended}"
        )

        return result

    async def _compute_skills_score(
        self,
        candidate_id: str,
        parsed_resume: Dict[str, Any],
        parsed_jd: Dict[str, Any],
    ) -> Tuple[float, List[Tuple[str, float]]]:
        """Compute skills match score using vector similarity."""
        required_skills = parsed_jd.get("must_have_skills", [])
        candidate_skills = parsed_resume.get("skills", [])

        if not required_skills:
            return 0.5, []  # Neutral if no requirements

        if not candidate_skills:
            return 0.0, []

        # Embed all skills
        req_embeddings = self.embeddings.embed_documents(required_skills)
        cand_embeddings = self.embeddings.embed_documents(candidate_skills)

        # Compute similarity matrix
        req_arr = np.array(req_embeddings)
        cand_arr = np.array(cand_embeddings)

        # Cosine similarity (already normalized)
        similarity_matrix = np.dot(req_arr, cand_arr.T)

        # For each required skill, find best matching candidate skill
        matched_skills = []
        total_score = 0.0

        for i, req_skill in enumerate(required_skills):
            best_match_idx = np.argmax(similarity_matrix[i])
            best_similarity = similarity_matrix[i, best_match_idx]

            if best_similarity >= self.config.similarity_threshold:
                matched_skills.append((req_skill, float(best_similarity)))
                total_score += best_similarity
            else:
                # Partial credit for close matches
                total_score += best_similarity * 0.5

        avg_score = total_score / len(required_skills)

        return float(min(1.0, avg_score)), matched_skills

    async def _compute_projects_score(
        self,
        candidate_id: str,
        parsed_resume: Dict[str, Any],
        parsed_jd: Dict[str, Any],
    ) -> Tuple[float, List[Tuple[str, float]]]:
        """Compute project relevance score."""
        projects = parsed_resume.get("projects", [])
        role_desc = parsed_jd.get("role", "") + " " + ", ".join(parsed_jd.get("competencies", []))

        if not projects or not role_desc.strip():
            return 0.5, []  # Neutral

        # Embed role description
        role_embedding = self.embeddings.embed_query(role_desc)

        # Embed each project
        project_texts = [p if isinstance(p, str) else str(p) for p in projects[:10]]
        project_embeddings = self.embeddings.embed_documents(project_texts)

        # Compute similarities
        role_arr = np.array(role_embedding)
        proj_arr = np.array(project_embeddings)

        similarities = np.dot(proj_arr, role_arr)

        matched_projects = []
        for i, proj in enumerate(project_texts):
            sim = similarities[i]
            if sim >= self.config.similarity_threshold:
                matched_projects.append((proj[:100], float(sim)))

        # Score is average of top 3 project matches
        top_scores = sorted(similarities, reverse=True)[:3]
        avg_score = np.mean(top_scores) if top_scores else 0.0

        return float(min(1.0, avg_score)), matched_projects

    async def _compute_experience_score(
        self,
        parsed_resume: Dict[str, Any],
        parsed_jd: Dict[str, Any],
    ) -> float:
        """Compute experience level match."""
        candidate_years = parsed_resume.get("experience_years", 0)
        required_range = parsed_jd.get("experience_range", "")

        if not required_range:
            return 0.5  # Neutral if no requirement

        # Parse experience range (e.g., "3-5 years")
        import re
        numbers = re.findall(r"\d+", required_range)

        if not numbers:
            return 0.5

        min_years = int(numbers[0])
        max_years = int(numbers[1]) if len(numbers) > 1 else min_years + 3

        # Score based on fit
        if candidate_years < min_years:
            # Under-qualified
            ratio = candidate_years / min_years if min_years > 0 else 0
            return min(0.7, ratio)
        elif candidate_years > max_years + 2:
            # Potentially over-qualified (slight penalty)
            return 0.8
        else:
            # Good fit
            return 1.0

    async def _compute_tools_score(
        self,
        candidate_id: str,
        parsed_resume: Dict[str, Any],
        parsed_jd: Dict[str, Any],
    ) -> Tuple[float, List[str]]:
        """Compute tools/technology match score."""
        required_tools = parsed_jd.get("tools", [])
        candidate_tools = parsed_resume.get("tools", [])

        if not required_tools:
            return 0.5, []

        if not candidate_tools:
            return 0.0, []

        # Use vector similarity for fuzzy matching
        req_embeddings = self.embeddings.embed_documents(required_tools)
        cand_embeddings = self.embeddings.embed_documents(candidate_tools)

        req_arr = np.array(req_embeddings)
        cand_arr = np.array(cand_embeddings)

        similarity_matrix = np.dot(req_arr, cand_arr.T)

        matched_tools = []
        total_score = 0.0

        for i, tool in enumerate(required_tools):
            best_similarity = np.max(similarity_matrix[i])
            if best_similarity >= 0.7:  # Higher threshold for tools
                matched_tools.append(tool)
                total_score += 1.0
            elif best_similarity >= 0.5:
                total_score += 0.5

        avg_score = total_score / len(required_tools) if required_tools else 0.5

        return float(min(1.0, avg_score)), matched_tools

    async def _get_top_matches(
        self,
        candidate_id: str,
        jd_id: str,
        k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Get top matching chunks between resume and JD."""
        # Get JD chunks
        jd_results = self.jd_db._collection.get(
            where={"jd_id": jd_id},
            include=["documents", "metadatas"],
        )

        if not jd_results["documents"]:
            return []

        # Query resume with each important JD chunk
        top_matches = []
        important_jd_chunks = [
            (doc, meta)
            for doc, meta in zip(jd_results["documents"], jd_results["metadatas"])
            if meta.get("importance") == "high"
        ][:3]

        for jd_chunk, jd_meta in important_jd_chunks:
            results = self.resumes_db.similarity_search_with_score(
                jd_chunk,
                k=2,
                filter={"candidate_id": candidate_id},
            )

            for doc, score in results:
                if score < 0.8:  # Cosine distance threshold
                    top_matches.append({
                        "jd_chunk_type": jd_meta.get("chunk_type"),
                        "resume_chunk": doc.page_content[:200],
                        "similarity": round(1 - score, 3),  # Convert distance to similarity
                    })

        # Sort by similarity and dedupe
        top_matches.sort(key=lambda x: x["similarity"], reverse=True)
        return top_matches[:5]

    def _generate_reasoning(
        self,
        skills_score: float,
        projects_score: float,
        experience_score: float,
        tools_score: float,
        matched_skills: List[Tuple[str, float]],
        final_score: float,
        threshold: float,
    ) -> str:
        """Generate human-readable reasoning for the match."""
        parts = []

        if skills_score >= 0.7:
            parts.append(f"Strong skills match ({skills_score:.0%})")
        elif skills_score >= 0.5:
            parts.append(f"Moderate skills match ({skills_score:.0%})")
        else:
            parts.append(f"Limited skills match ({skills_score:.0%})")

        if projects_score >= 0.7:
            parts.append("relevant project experience")
        elif projects_score < 0.4:
            parts.append("limited relevant projects")

        if experience_score >= 0.9:
            parts.append("experience level fits well")
        elif experience_score < 0.5:
            parts.append("experience level mismatch")

        if matched_skills:
            top_skills = [s for s, _ in matched_skills[:3]]
            parts.append(f"matched skills: {', '.join(top_skills)}")

        summary = "; ".join(parts)

        if final_score >= threshold:
            return f"Recommended for shortlist. {summary}"
        else:
            gap = threshold - final_score
            return f"Below threshold by {gap:.0%}. {summary}"

    # ─── Batch Processing ─────────────────────────────────────────────────────

    async def batch_evaluate_candidates(
        self,
        candidate_ids: List[str],
        jd_id: str,
        parsed_jd: Dict[str, Any],
        parsed_resumes: Dict[str, Dict[str, Any]],
    ) -> List[SemanticMatchResult]:
        """
        Evaluate multiple candidates against a JD in parallel.

        Args:
            candidate_ids: List of candidate IDs to evaluate
            jd_id: JD identifier
            parsed_jd: Parsed JD data
            parsed_resumes: Dict mapping candidate_id -> parsed resume

        Returns:
            List of SemanticMatchResult sorted by score descending
        """
        tasks = [
            self.compute_semantic_match(
                candidate_id=cid,
                jd_id=jd_id,
                parsed_resume=parsed_resumes.get(cid, {}),
                parsed_jd=parsed_jd,
            )
            for cid in candidate_ids
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out errors and sort
        valid_results = [r for r in results if isinstance(r, SemanticMatchResult)]
        valid_results.sort(key=lambda r: r.final_score, reverse=True)

        return valid_results

    # ─── Answer Similarity ────────────────────────────────────────────────────

    def compute_answer_similarity(self, question: str, answer: str) -> float:
        """
        Compute semantic similarity between question and answer.
        Used for cheating detection (high similarity = parroting).

        Args:
            question: The interview question
            answer: Candidate's answer

        Returns:
            Similarity score (0-1, higher = more similar)
        """
        q_embedding = self.embeddings.embed_query(question)
        a_embedding = self.embeddings.embed_query(answer)

        # Cosine similarity (embeddings are normalized)
        similarity = np.dot(q_embedding, a_embedding)

        return float(max(0.0, min(1.0, similarity)))

    # ─── Cleanup ──────────────────────────────────────────────────────────────

    async def delete_candidate(self, candidate_id: str) -> None:
        """Remove all data for a candidate."""
        try:
            self.resumes_db._collection.delete(where={"candidate_id": candidate_id})
            logger.info(f"Deleted embeddings for candidate {candidate_id}")
        except Exception as e:
            logger.error(f"Failed to delete candidate {candidate_id}: {e}")

    async def delete_jd(self, jd_id: str) -> None:
        """Remove all data for a JD."""
        try:
            self.jd_db._collection.delete(where={"jd_id": jd_id})
            logger.info(f"Deleted embeddings for JD {jd_id}")
        except Exception as e:
            logger.error(f"Failed to delete JD {jd_id}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON
# ═══════════════════════════════════════════════════════════════════════════════


_enhanced_chroma_instance: Optional[EnhancedChromaService] = None


def get_enhanced_chroma_service() -> EnhancedChromaService:
    """Get the enhanced ChromaDB service singleton."""
    global _enhanced_chroma_instance
    if _enhanced_chroma_instance is None:
        _enhanced_chroma_instance = EnhancedChromaService()
    return _enhanced_chroma_instance
