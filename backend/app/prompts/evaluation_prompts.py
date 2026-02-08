"""
Evaluation Prompts - Post-interview evaluation and scoring

These prompts are used after the interview completes to generate
reference answers, score responses, and aggregate results.
"""

from langchain_core.prompts import ChatPromptTemplate


# ═══════════════════════════════════════════════════════════════════════════
# REFERENCE ANSWER GENERATION
# ═══════════════════════════════════════════════════════════════════════════

REFERENCE_ANSWER_PROMPT = ChatPromptTemplate.from_template(
    """Generate a reference answer that a strong candidate would give.

QUESTION:
{question}

CONTEXT:
- Topic: {pillar_name}
- Job Role: {job_role}
- Difficulty Level: {depth_level}/5
- Time Constraint: {time_constraint}

INSTRUCTIONS:
Create a reference answer that:
1. Is achievable in {time_constraint} of speaking
2. Covers all essential points clearly
3. Demonstrates appropriate depth for level {depth_level}
4. Represents what a "hire" candidate would say

Also identify:
- Key points that MUST be covered
- Advanced points that show expertise
- Common mistakes to watch for

OUTPUT FORMAT (JSON only, no markdown):
{{
    "reference_answer": "The complete reference answer a strong candidate would give...",
    "key_points": ["Essential point 1", "Essential point 2", "Essential point 3"],
    "advanced_points": ["Advanced point showing expertise"],
    "common_mistakes": ["Common mistake 1", "Misconception to watch for"],
    "difficulty_assessment": "basic|intermediate|advanced|expert"
}}"""
)


# ═══════════════════════════════════════════════════════════════════════════
# RUBRIC SCORING
# ═══════════════════════════════════════════════════════════════════════════

RUBRIC_SCORING_PROMPT = ChatPromptTemplate.from_template(
    """Score this candidate answer against the reference using a structured rubric.

QUESTION:
{question}

CANDIDATE'S ANSWER:
{candidate_answer}

REFERENCE ANSWER:
{reference_answer}

KEY POINTS (must cover):
{key_points}

ADVANCED POINTS (bonus):
{advanced_points}

COMMON MISTAKES (deduct if present):
{common_mistakes}

SCORING RUBRIC (1-5 scale):

CORRECTNESS (accuracy vs reference):
5 = Completely accurate, no errors
4 = Mostly accurate, minor issues
3 = Partially correct, some errors
2 = Significant errors but shows understanding
1 = Mostly incorrect or irrelevant

DEPTH (technical comprehensiveness):
5 = Exceptional depth, covers advanced points
4 = Good depth, covers all key points
3 = Adequate depth, covers most key points
2 = Shallow, misses important points
1 = Superficial or missing depth

REASONING (quality of explanation):
5 = Excellent logical flow, clear rationale
4 = Good reasoning, well-connected ideas
3 = Adequate reasoning, some gaps
2 = Weak reasoning, jumps in logic
1 = No clear reasoning

CLARITY (communication quality):
5 = Crystal clear, well-structured
4 = Clear, minor ambiguities
3 = Understandable but could be clearer
2 = Confusing in places
1 = Unclear or poorly structured

OUTPUT FORMAT (JSON only, no markdown):
{{
    "correctness": {{
        "dimension": "correctness",
        "score": 1-5,
        "justification": "Brief justification"
    }},
    "depth": {{
        "dimension": "depth",
        "score": 1-5,
        "justification": "Brief justification"
    }},
    "reasoning": {{
        "dimension": "reasoning",
        "score": 1-5,
        "justification": "Brief justification"
    }},
    "clarity": {{
        "dimension": "clarity",
        "score": 1-5,
        "justification": "Brief justification"
    }},
    "overall_score": 1.0-5.0,
    "normalized_score": 0.0-100.0,
    "strength_areas": ["area1", "area2"],
    "improvement_areas": ["area1", "area2"],
    "coverage_percentage": 0.0-100.0,
    "advanced_points_hit": 0
}}"""
)


# ═══════════════════════════════════════════════════════════════════════════
# EVALUATION AGGREGATION
# ═══════════════════════════════════════════════════════════════════════════

EVALUATION_AGGREGATE_PROMPT = ChatPromptTemplate.from_template(
    """Aggregate individual question scores into overall metrics.

INDIVIDUAL SCORES:
{individual_scores}

PILLARS COVERED: {pillar_names}
TOTAL QUESTIONS: {total_questions}
CHEATING FLAGS: {cheating_flags}
WEIGHT SCHEME: {weights}

INSTRUCTIONS:
1. Calculate per-pillar averages
2. Calculate dimension averages (correctness, depth, reasoning, clarity)
3. Identify strongest and weakest pillars
4. Determine performance trajectory
5. Apply cheating deductions if applicable

CHEATING DEDUCTION RULES:
- WARNING_1: -5 points
- WARNING_2: -10 points
- PENALTY: -25 points or disqualification

OUTPUT FORMAT (JSON only, no markdown):
{{
    "total_questions": {total_questions},
    "total_follow_ups": <count>,
    "overall_score": 0.0-100.0,
    "confidence_interval": [lower, upper],
    "pillar_summaries": [
        {{
            "pillar_name": "name",
            "questions_count": n,
            "average_score": 0.0-100.0,
            "strongest_area": "area or null",
            "weakest_area": "area or null",
            "key_observations": ["obs1", "obs2"]
        }}
    ],
    "average_correctness": 0.0-100.0,
    "average_depth": 0.0-100.0,
    "average_reasoning": 0.0-100.0,
    "average_clarity": 0.0-100.0,
    "strongest_pillars": ["pillar1"],
    "weakest_pillars": ["pillar1"],
    "improvement_trajectory": "improving|declining|stable|inconsistent",
    "cheating_deductions": 0.0,
    "adjusted_score": 0.0-100.0
}}"""
)


# ═══════════════════════════════════════════════════════════════════════════
# BATCH REFERENCE GENERATION
# ═══════════════════════════════════════════════════════════════════════════

BATCH_REFERENCE_GENERATION_PROMPT = ChatPromptTemplate.from_template(
    """Generate reference answers for these interview questions.

JOB ROLE: {job_role}
JOB REQUIREMENTS: {job_requirements}

QUESTIONS:
{questions_json}

For each question, provide:
1. A reference answer (45 seconds of speaking)
2. Key points that must be covered
3. Difficulty assessment

OUTPUT FORMAT (JSON array, no markdown):
[
    {{
        "question_id": "q1",
        "reference_answer": "...",
        "key_points": ["...", "..."],
        "difficulty_assessment": "basic|intermediate|advanced|expert"
    }},
    ...
]"""
)
