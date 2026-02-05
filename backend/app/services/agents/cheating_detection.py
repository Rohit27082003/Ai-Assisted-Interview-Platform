"""Cheating Detection Agent.

Runs parallel to transcription. Detects:
  - Question parroting (high semantic similarity between Q and A)
  - Low novel token count
  - Pattern repetition

Escalation: warning_1 → warning_2 → penalty
"""

from typing import Dict, Any, List
from app.services.vector_store.chroma_service import get_chroma_service
from app.core.llm import get_llm
from langchain_core.prompts import ChatPromptTemplate
from app.core.logging import get_logger

logger = get_logger(__name__)

# Thresholds
SIMILARITY_THRESHOLD = 0.80
LOW_NOVEL_TOKEN_RATIO = 0.30
MIN_ANSWER_LENGTH = 10


class CheatingDetector:
    """Detects potential cheating during interview."""

    def __init__(self):
        self.chroma = get_chroma_service()
        self.flags: List[Dict[str, Any]] = []

    async def analyze(
        self,
        question: str,
        answer: str,
        question_number: int,
        existing_flags: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Analyze a Q&A pair for cheating indicators.

        Returns:
            {
                "is_flagged": bool,
                "level": "none" | "warning_1" | "warning_2" | "penalty",
                "reasons": [],
                "similarity_score": float,
                "novel_token_ratio": float,
            }
        """
        self.flags = existing_flags or []
        reasons = []
        is_flagged = False

        # Check 1: Semantic similarity between question and answer
        similarity = self._compute_qa_similarity(question, answer)

        # Check 2: Novel token ratio
        novel_ratio = self._compute_novel_token_ratio(question, answer)

        # Check 3: Answer too short (possible evasion)
        answer_words = len(answer.strip().split())

        # Pattern 1: Question parroting
        if similarity > SIMILARITY_THRESHOLD and novel_ratio < LOW_NOVEL_TOKEN_RATIO:
            reasons.append(
                f"Answer closely mirrors the question (similarity={similarity:.2f}, "
                f"novel_ratio={novel_ratio:.2f})"
            )
            is_flagged = True

        # Pattern 2: Extremely short answer
        if answer_words < MIN_ANSWER_LENGTH and answer.strip():
            reasons.append(f"Very short answer ({answer_words} words)")
            is_flagged = True

        # Pattern 3: LLM-based suspicion check for sophisticated cheating
        if not is_flagged and answer_words > 20:
            llm_check = await self._llm_cheating_check(question, answer)
            if llm_check.get("suspicious"):
                reasons.append(llm_check.get("reason", "LLM flagged as suspicious"))
                is_flagged = True

        # Determine escalation level
        current_flag_count = len(self.flags)
        if is_flagged:
            if current_flag_count == 0:
                level = "warning_1"
            elif current_flag_count == 1:
                level = "warning_2"
            else:
                level = "penalty"
        else:
            level = "none"

        result = {
            "is_flagged": is_flagged,
            "level": level,
            "reasons": reasons,
            "similarity_score": round(similarity, 4),
            "novel_token_ratio": round(novel_ratio, 4),
            "question_number": question_number,
        }

        if is_flagged:
            logger.warning(
                f"Cheating detected: level={level}, reasons={reasons}"
            )

        return result

    def _compute_qa_similarity(self, question: str, answer: str) -> float:
        """Compute semantic similarity between question and answer."""
        try:
            return self.chroma.check_answer_similarity(question, answer)
        except Exception as e:
            logger.error(f"Similarity computation failed: {e}")
            return 0.0

    def _compute_novel_token_ratio(self, question: str, answer: str) -> float:
        """Compute the ratio of tokens in the answer that are NOT in the question."""
        q_tokens = set(question.lower().split())
        a_tokens = answer.lower().split()

        if not a_tokens:
            return 0.0

        novel = [t for t in a_tokens if t not in q_tokens]
        return len(novel) / len(a_tokens)

    async def _llm_cheating_check(self, question: str, answer: str) -> Dict[str, Any]:
        """Use LLM to check for sophisticated cheating patterns."""
        try:
            llm = get_llm(temperature=0.1)
            prompt = ChatPromptTemplate.from_messages([
                ("system", """You are an interview integrity checker. Analyze if the answer shows signs of:
1. Reading from a pre-prepared script (unnaturally perfect, textbook-like)
2. Being dictated by someone else (inconsistent expertise level)
3. Being copy-pasted from a source (overly formal, includes references)

Question: {question}
Answer: {answer}

Return ONLY a JSON: {{"suspicious": true/false, "reason": "brief explanation"}}
Do not include any markdown formatting."""),
                ("human", "Analyze this Q&A pair."),
            ])
            chain = prompt | llm
            response = await chain.ainvoke({
                "question": question,
                "answer": answer,
            })
            import json
            return json.loads(response.content)
        except Exception as e:
            logger.error(f"LLM cheating check failed: {e}")
            return {"suspicious": False, "reason": ""}


def get_cheating_detector() -> CheatingDetector:
    return CheatingDetector()
