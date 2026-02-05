"""ChromaDB vector store service for semantic matching."""

import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Any, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class ChromaService:
    """Manages ChromaDB collections for semantic reasoning."""

    RESUMES_COLLECTION = "resumes_collection"
    JD_COLLECTION = "jd_collection"

    def __init__(self):
        self.client = chromadb.Client(ChromaSettings(
            anonymized_telemetry=False,
        ))
        self._ensure_collections()

    def _ensure_collections(self):
        """Create collections if they don't exist."""
        self.resumes_col = self.client.get_or_create_collection(
            name=self.RESUMES_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self.jd_col = self.client.get_or_create_collection(
            name=self.JD_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    def add_resume_chunks(
        self,
        candidate_id: str,
        chunks: List[str],
        metadata_list: List[Dict[str, Any]],
    ) -> List[str]:
        """Add resume chunks with metadata to the resumes collection."""
        ids = [f"{candidate_id}_chunk_{i}" for i in range(len(chunks))]
        enriched_meta = []
        for m in metadata_list:
            meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in m.items()}
            meta["candidate_id"] = candidate_id
            enriched_meta.append(meta)

        self.resumes_col.add(
            documents=chunks,
            metadatas=enriched_meta,
            ids=ids,
        )
        logger.info(f"Added {len(chunks)} resume chunks for candidate {candidate_id}")
        return ids

    def add_jd_chunks(
        self,
        jd_id: str,
        chunks: List[str],
        metadata_list: List[Dict[str, Any]],
    ) -> List[str]:
        """Add JD chunks to the JD collection."""
        ids = [f"{jd_id}_chunk_{i}" for i in range(len(chunks))]
        enriched_meta = []
        for m in metadata_list:
            meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in m.items()}
            meta["jd_id"] = jd_id
            enriched_meta.append(meta)

        self.jd_col.add(
            documents=chunks,
            metadatas=enriched_meta,
            ids=ids,
        )
        logger.info(f"Added {len(chunks)} JD chunks for JD {jd_id}")
        return ids

    def semantic_match(
        self,
        query_texts: List[str],
        collection_name: str,
        n_results: int = 5,
        where_filter: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Perform semantic search against a collection."""
        collection = (
            self.resumes_col
            if collection_name == self.RESUMES_COLLECTION
            else self.jd_col
        )
        kwargs = {
            "query_texts": query_texts,
            "n_results": n_results,
        }
        if where_filter:
            kwargs["where"] = where_filter

        results = collection.query(**kwargs)
        return results

    def compute_similarity_score(
        self, resume_candidate_id: str, jd_id: str
    ) -> float:
        """Compute semantic similarity between a resume and JD."""
        # Get all JD chunks
        jd_results = self.jd_col.get(
            where={"jd_id": jd_id},
            include=["documents"],
        )
        if not jd_results["documents"]:
            return 0.0

        jd_texts = jd_results["documents"]

        # Query resume collection with JD text
        match_results = self.resumes_col.query(
            query_texts=jd_texts,
            n_results=3,
            where={"candidate_id": resume_candidate_id},
        )

        if not match_results["distances"]:
            return 0.0

        # Chroma cosine distance: 0 = identical, 2 = opposite
        # Convert to similarity: 1 - (distance / 2)
        all_distances = []
        for dist_list in match_results["distances"]:
            all_distances.extend(dist_list)

        if not all_distances:
            return 0.0

        avg_distance = sum(all_distances) / len(all_distances)
        similarity = 1.0 - (avg_distance / 2.0)
        return max(0.0, min(1.0, similarity))

    def check_answer_similarity(self, question: str, answer: str) -> float:
        """Check semantic similarity between question and answer for cheating detection."""
        # Use a temporary collection approach
        temp_col = self.client.get_or_create_collection(name="_temp_similarity")
        temp_id = "temp_q"
        try:
            temp_col.add(documents=[question], ids=[temp_id])
            results = temp_col.query(query_texts=[answer], n_results=1)
            if results["distances"] and results["distances"][0]:
                distance = results["distances"][0][0]
                similarity = 1.0 - (distance / 2.0)
                return max(0.0, min(1.0, similarity))
        finally:
            self.client.delete_collection("_temp_similarity")
        return 0.0


_chroma_instance: Optional[ChromaService] = None


def get_chroma_service() -> ChromaService:
    global _chroma_instance
    if _chroma_instance is None:
        _chroma_instance = ChromaService()
    return _chroma_instance
