"""ChromaDB vector store service using LangChain components."""

from typing import List, Dict, Any, Optional
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from app.core.logging import get_logger

logger = get_logger(__name__)


class ChromaService:
    """Manages ChromaDB collections using LangChain abstractions."""

    RESUMES_COLLECTION = "resumes_collection"
    JD_COLLECTION = "jd_collection"

    def __init__(self):
        # Initialize embeddings (lightweight model)
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        
        # Initialize vector stores (in-memory for now to match previous behavior)
        # Note: In production, providing a persist_directory would be better.
        self.resumes_db = Chroma(
            collection_name=self.RESUMES_COLLECTION,
            embedding_function=self.embeddings,
            collection_metadata={"hnsw:space": "cosine"}
        )
        self.jd_db = Chroma(
            collection_name=self.JD_COLLECTION,
            embedding_function=self.embeddings,
            collection_metadata={"hnsw:space": "cosine"}
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
            # Flatten/stringify complex metadata just in case, though LangChain handles most types
            meta = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v for k, v in m.items()}
            meta["candidate_id"] = candidate_id
            enriched_meta.append(meta)

        self.resumes_db.add_texts(
            texts=chunks,
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

        self.jd_db.add_texts(
            texts=chunks,
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
        """Perform semantic search against a collection.
        
        Returns a dict similar to raw Chroma query result for compatibility, 
        or a list of documents if the caller adapts.
        For backwards compatibility with existing graph code, we'll try to match the return structure
        if existing code expects 'documents', 'distances', 'metadatas'.
        """
        db = (
            self.resumes_db
            if collection_name == self.RESUMES_COLLECTION
            else self.jd_db
        )
        
        # NOTE: LangChain's standard similarity_search doesn't return distances by default,
        # and returns Document objects. 
        # If the caller expects specific Chroma-style output format, we might need to conform.
        # Based on previous code, this method was barely used or return type wasn't strictly checked?
        # Let's use similarity_search_with_score to get distances.
        
        results = []
        # Support batch queries? LangChain usually does single query.
        # If query_texts has multiple, we iterate.
        all_docs = []
        all_distances = []
        all_metadatas = []
        
        for q in query_texts:
            # score in Chroma + LangChain is usually distance (lower is better for cosine)
            # or similarity score depending on settings. 
            # With hnsw:space=cosine, likely returns distance strings.
            docs_and_scores = db.similarity_search_with_score(
                q, k=n_results, filter=where_filter
            )
            
            # Unpack
            q_docs = [d.page_content for d, s in docs_and_scores]
            q_metas = [d.metadata for d, s in docs_and_scores]
            q_dists = [s for d, s in docs_and_scores]
            
            all_docs.append(q_docs)
            all_metadatas.append(q_metas)
            all_distances.append(q_dists)

        return {
            "ids": [], # IDs not easily retrieved from standard LC Document unless stored in metadata
            "documents": all_docs,
            "metadatas": all_metadatas,
            "distances": all_distances,
        }

    def compute_similarity_score(
        self, resume_candidate_id: str, jd_id: str
    ) -> float:
        """Compute semantic similarity between a resume and JD."""
        # Get all JD chunks - efficiently via filter if possible, or just fetch all logic needs re-thought for LC
        # LangChain doesn't support "get all by filter" easily without underlying client access.
        # We can access ._collection (the raw Chroma collection) if absolutely needed, 
        # OR just use similarity search.
        
        # Accessing raw collection for 'get' functionality is acceptable given the constraints
        jd_results = self.jd_db._collection.get(
            where={"jd_id": jd_id},
            include=["documents"],
        )
        
        if not jd_results["documents"]:
            return 0.0

        jd_texts = jd_results["documents"]

        # Now query resume DB with JD texts
        # We can use our semantic_match wrapper which handles the batch query loop
        match_results = self.semantic_match(
            query_texts=jd_texts,
            collection_name=self.RESUMES_COLLECTION,
            n_results=3,
            where_filter={"candidate_id": resume_candidate_id}
        )

        if not match_results["distances"]:
            return 0.0

        all_distances = []
        for dist_list in match_results["distances"]:
            all_distances.extend(dist_list)

        if not all_distances:
            return 0.0

        avg_distance = sum(all_distances) / len(all_distances)
        # Cosine distance to similarity: 1 - (dist / 2) is common approx for angular, 
        # or simplified 1 - dist if normalized. Chroma default is usually Cosine Distance [0, 2].
        similarity = 1.0 - (avg_distance / 2.0)
        return max(0.0, min(1.0, similarity))

    def check_answer_similarity(self, question: str, answer: str) -> float:
        """Check semantic similarity using embedding distance directly."""
        # Embed single strings
        q_emb = self.embeddings.embed_query(question)
        a_emb = self.embeddings.embed_query(answer)
        
        # Calculate cosine similarity manually
        # Cosine Sim = (A . B) / (||A|| * ||B||)
        # HuggingFace embeddings usually normalized? If so dot product is cosine sim.
        
        import numpy as np
        vec_q = np.array(q_emb)
        vec_a = np.array(a_emb)
        
        norm_q = np.linalg.norm(vec_q)
        norm_a = np.linalg.norm(vec_a)
        
        if norm_q == 0 or norm_a == 0:
            return 0.0
            
        cos_sim = np.dot(vec_q, vec_a) / (norm_q * norm_a)
        return float(max(0.0, min(1.0, cos_sim)))


_chroma_instance: Optional[ChromaService] = None


def get_chroma_service() -> ChromaService:
    global _chroma_instance
    if _chroma_instance is None:
        _chroma_instance = ChromaService()
    return _chroma_instance
