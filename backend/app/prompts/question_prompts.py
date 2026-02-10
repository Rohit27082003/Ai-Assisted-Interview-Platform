from langchain_core.prompts import ChatPromptTemplate

# ═══════════════════════════════════════════════════════════════════════════
# QUESTION GENERATION
# ═══════════════════════════════════════════════════════════════════════════

QUESTION_GENERATION_PROMPT = ChatPromptTemplate.from_template(
    """You are an expert technical interviewer conducting a structured interview.

ROLE CONTEXT:
- Job Role: {job_role}
- Current Topic/Pillar: {pillar_name}
- Why This Topic: {pillar_reason}
- Difficulty Level: {depth_level}/5 (1=Foundational, 2=Practical, 3=Scenario, 4=Edge Case, 5=Expert)

CANDIDATE CONTEXT:
{resume_context}

CONVERSATION SO FAR:
{conversation_context}

TOPICS ALREADY COVERED (avoid repetition):
{previous_topics_covered}

CONCEPTS TO AVOID:
{avoid_concepts}

INSTRUCTIONS:
Generate ONE interview question that:
1. Directly probes the candidate's knowledge of "{pillar_name}"
2. Matches difficulty level {depth_level}/5
3. Is concise and readable in 12-15 seconds (max 30-40 words)
4. Can be answered in 45 seconds of speaking
5. Has a clear, assessable answer (not open-ended philosophy)
6. Builds on or differs from previous questions in this topic
7. Uses simple, direct language without complex nested clauses

DIFFICULTY LEVEL GUIDE:
- Level 1 (Foundational): Core concepts, definitions, basic understanding
- Level 2 (Practical): Application of concepts, common use cases
- Level 3 (Scenario): Real-world problem solving, trade-off analysis
- Level 4 (Edge Case): Unusual situations, failure modes, optimizations
- Level 5 (Expert): Deep internals, advanced patterns, architecture decisions

OUTPUT FORMAT (JSON only, no markdown):
{{
    "question": "Your question here",
    "question_type": "conceptual|practical|scenario|edge_case|expert",
    "depth_level": {depth_level},
    "target_skill": "Specific skill being tested",
    "expected_coverage": ["Key point 1", "Key point 2", "Key point 3"],
    "time_estimate_seconds": 45,
    "probing_intent": "What this question reveals about the candidate"
}}"""
)


# ═══════════════════════════════════════════════════════════════════════════
# FOLLOW-UP QUESTION GENERATION
# ═══════════════════════════════════════════════════════════════════════════

FOLLOW_UP_QUESTION_PROMPT = ChatPromptTemplate.from_template(
    """You are conducting a technical interview follow-up.

ORIGINAL QUESTION:
{original_question}

CANDIDATE'S ANSWER:
{candidate_answer}

TOPIC AREA: {pillar_name}
REASON FOR FOLLOW-UP: {follow_up_reason}
IDENTIFIED GAPS: {gaps_identified}
AREA TO PROBE: {probe_area}

INSTRUCTIONS:
Generate a targeted follow-up question that:
1. Does NOT change the topic - stays within "{pillar_name}"
2. Probes deeper into "{probe_area}"
3. References something specific from their answer
4. Is concise and readable in 10-15 seconds (max 25-30 words)
5. Can be answered in 30-45 seconds
6. Clarifies understanding or tests depth
7. Uses simple, direct language

OUTPUT FORMAT (JSON only, no markdown):
{{
    "follow_up_question": "Your follow-up question here",
    "builds_on": "What part of their answer this builds on",
    "gap_addressed": "What gap or unclear point this addresses",
    "expected_elaboration": ["Point they should elaborate on 1", "Point 2"]
}}"""
)


# ═══════════════════════════════════════════════════════════════════════════
# FOLLOW-UP DECISION (OPTIONAL LLM ASSIST)
# ═══════════════════════════════════════════════════════════════════════════

FOLLOW_UP_DECISION_PROMPT = ChatPromptTemplate.from_template(
    """Analyze whether a follow-up question is warranted.

QUESTION ASKED:
{question}

CANDIDATE'S ANSWER:
{answer}

ANALYSIS SIGNALS:
{analysis_signals}

CONSTRAINTS:
- Follow-ups remaining for this question: {follow_ups_remaining}
- Questions remaining in this pillar: {pillar_questions_remaining}

DECISION CRITERIA:
1. Follow up if answer was partial but shows potential for depth
2. Follow up if there's a specific gap worth probing
3. Do NOT follow up if answer was complete or clearly lacking
4. Do NOT follow up if running low on time/questions
5. Prefer moving forward if candidate seems stuck

OUTPUT FORMAT (JSON only, no markdown):
{{
    "should_follow_up": true|false,
    "reason": "Explanation for this decision",
    "follow_up_type": "clarification|deeper_probe|alternative_angle|verification|null",
    "confidence": 0.0-1.0,
    "follow_up_focus": "What to focus on if following up, or null"
}}"""
)
