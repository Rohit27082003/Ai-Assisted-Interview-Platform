"""
Analysis Prompts - Answer analysis and cheating detection

These prompts are used by the answer_analyzer node to evaluate
candidate responses and detect potential cheating.
"""

from .registry import PromptTemplate


ANALYSIS_PROMPTS = [
    # ═══════════════════════════════════════════════════════════════════════════
    # ANSWER ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="answer_analysis",
        version="2.0.0",
        description="Analyze a candidate's answer for quality signals",
        required_vars=["question", "answer", "pillar_name", "expected_coverage"],
        optional_vars={
            "depth_level": "3",
            "time_taken_seconds": "45",
            "is_follow_up": "false",
        },
        output_schema="AnswerAnalysisOutput",
        template="""You are evaluating a candidate's technical interview answer.

QUESTION ASKED:
{question}

CANDIDATE'S ANSWER:
{answer}

CONTEXT:
- Topic/Pillar: {pillar_name}
- Expected Difficulty: {depth_level}/5
- Time Taken: {time_taken_seconds} seconds
- Is Follow-up: {is_follow_up}

EXPECTED COVERAGE (key points a good answer should include):
{expected_coverage}

INSTRUCTIONS:
Analyze the answer objectively. Focus on:
1. Does it address the question? (relevance)
2. Is it factually correct? (correctness)
3. Does it demonstrate understanding? (depth)
4. Is it well-explained? (clarity)
5. Are there gaps worth probing? (follow-up potential)

Be calibrated: a 7/10 means "good but not exceptional."
A perfect 10/10 is rare and requires comprehensive, expert-level response.

OUTPUT FORMAT (JSON only, no markdown):
{{
    "is_relevant": true|false,
    "relevance_score": 0.0-10.0,
    "correctness_score": 0.0-10.0,
    "depth_score": 0.0-10.0,
    "clarity_score": 0.0-10.0,
    "key_concepts_covered": ["concept1", "concept2"],
    "missing_concepts": ["missing1", "missing2"],
    "misconceptions": ["any incorrect statements"],
    "has_probeable_gaps": true|false,
    "suggested_probe_areas": ["area1", "area2"],
    "overall_signal_score": 0.0-10.0,
    "analysis_summary": "One sentence summary"
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # CHEATING DETECTION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="cheating_detection",
        version="2.0.0",
        description="Detect potential cheating patterns in an answer",
        required_vars=["question", "answer", "question_number"],
        optional_vars={
            "previous_answer_quality": "moderate",
            "time_to_respond_seconds": "30",
            "candidate_demonstrated_level": "intermediate",
        },
        output_schema="CheatingDetectionOutput",
        template="""Analyze this interview answer for potential cheating indicators.

QUESTION #{question_number}:
{question}

CANDIDATE'S ANSWER:
{answer}

CONTEXT:
- Previous Answer Quality: {previous_answer_quality}
- Time to Respond: {time_to_respond_seconds} seconds
- Candidate's Demonstrated Level: {candidate_demonstrated_level}

CHEATING INDICATORS TO CHECK:
1. QUESTION PARROTING: Does the answer simply repeat the question with minimal elaboration?
2. UNNATURAL FLUENCY: Is the answer suspiciously polished, with perfect formatting or structure that suggests copy-pasting?
3. VOCABULARY MISMATCH: Does the vocabulary/terminology level not match the candidate's demonstrated knowledge?
4. RESPONSE TIMING: Was the response too fast for the complexity, or suspiciously well-formed for the time?
5. CONSISTENCY: Is the quality dramatically different from previous answers?
6. AI PATTERNS: Does it have hallmarks of AI-generated content (generic structure, hedging language, list format)?

BE FAIR:
- A strong candidate CAN give excellent answers - don't flag knowledge as cheating
- Some candidates are naturally articulate - this isn't cheating
- Focus on PATTERNS that suggest external help, not just quality

OUTPUT FORMAT (JSON only, no markdown):
{{
    "is_suspicious": true|false,
    "suspicion_score": 0.0-10.0,
    "pattern_flags": ["specific suspicious pattern 1", "pattern 2"],
    "question_parroting_score": 0.0-10.0,
    "unnatural_fluency_score": 0.0-10.0,
    "response_timing_flag": true|false,
    "vocabulary_mismatch": true|false,
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of assessment",
    "recommended_action": "continue|warn|flag|escalate"
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # CHEATING ESCALATION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="cheating_escalation",
        version="1.0.0",
        description="Determine cheating escalation based on accumulated flags",
        required_vars=["current_level", "accumulated_flags", "flag_count"],
        optional_vars={
            "interview_progress": "50%",
        },
        output_schema="CheatingEscalationOutput",
        template="""Evaluate whether to escalate cheating level based on accumulated evidence.

CURRENT CHEATING LEVEL: {current_level}
TOTAL FLAGS: {flag_count}
INTERVIEW PROGRESS: {interview_progress}

ACCUMULATED FLAGS:
{accumulated_flags}

ESCALATION RULES:
- NONE → WARNING_1: First clear cheating indicator
- WARNING_1 → WARNING_2: Second distinct cheating indicator
- WARNING_2 → PENALTY: Third indicator OR severe single violation
- PENALTY: Interview should be terminated

Consider:
1. Severity of each flag
2. Whether flags are correlated (same issue) or distinct
3. Pattern across multiple questions vs isolated incident
4. Interview progress (early flags may indicate ongoing issue)

OUTPUT FORMAT (JSON only, no markdown):
{{
    "current_level": "{current_level}",
    "escalate_to": "none|warning_1|warning_2|penalty|null",
    "should_terminate": true|false,
    "termination_reason": "reason if terminating, else null",
    "cumulative_evidence": ["summary of key evidence points"]
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # QUICK RELEVANCE CHECK
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="quick_relevance_check",
        version="1.0.0",
        description="Quick check if answer is relevant (for fast filtering)",
        required_vars=["question", "answer"],
        template="""Does this answer attempt to address the question?

QUESTION: {question}
ANSWER: {answer}

Reply with ONLY "relevant" or "irrelevant" (one word, lowercase).""",
    ),
]
