"""
Interview Prompts - Question generation and follow-up prompts

These prompts are used by the question_engine node to generate
interview questions and decide on follow-ups.
"""

from .registry import PromptTemplate


INTERVIEW_PROMPTS = [
    # ═══════════════════════════════════════════════════════════════════════════
    # QUESTION GENERATION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="question_generation",
        version="2.0.0",
        description="Generate an interview question for a specific pillar and depth",
        required_vars=["pillar_name", "pillar_reason", "depth_level", "job_role"],
        optional_vars={
            "resume_context": "",
            "conversation_context": "",
            "previous_topics_covered": "",
            "avoid_concepts": "",
        },
        output_schema="QuestionGenerationOutput",
        template="""You are an expert technical interviewer conducting a structured interview.

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
3. Can be answered in 45 seconds of speaking
4. Has a clear, assessable answer (not open-ended philosophy)
5. Builds on or differs from previous questions in this topic

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
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # FOLLOW-UP QUESTION GENERATION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="follow_up_question",
        version="2.0.0",
        description="Generate a follow-up question based on a previous answer",
        required_vars=[
            "original_question",
            "candidate_answer",
            "probe_area",
            "pillar_name",
        ],
        optional_vars={
            "follow_up_reason": "",
            "gaps_identified": "",
        },
        output_schema="FollowUpQuestionOutput",
        template="""You are conducting a technical interview follow-up.

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
4. Can be answered in 30-45 seconds
5. Clarifies understanding or tests depth

OUTPUT FORMAT (JSON only, no markdown):
{{
    "follow_up_question": "Your follow-up question here",
    "builds_on": "What part of their answer this builds on",
    "gap_addressed": "What gap or unclear point this addresses",
    "expected_elaboration": ["Point they should elaborate on 1", "Point 2"]
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # FOLLOW-UP DECISION (OPTIONAL LLM ASSIST)
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="follow_up_decision",
        version="2.0.0",
        description="Decide whether a follow-up question is needed (LLM-assisted)",
        required_vars=["question", "answer", "analysis_signals"],
        optional_vars={
            "follow_ups_remaining": "2",
            "pillar_questions_remaining": "3",
        },
        output_schema="FollowUpDecisionOutput",
        template="""Analyze whether a follow-up question is warranted.

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
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # PILLAR TRANSITION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="pillar_transition",
        version="1.0.0",
        description="Generate a smooth transition message between pillars",
        required_vars=["previous_pillar", "next_pillar", "candidate_name"],
        optional_vars={
            "previous_performance_summary": "You did well in the previous section.",
        },
        template="""Generate a brief, professional transition message.

PREVIOUS TOPIC: {previous_pillar}
NEXT TOPIC: {next_pillar}
CANDIDATE: {candidate_name}
PREVIOUS PERFORMANCE: {previous_performance_summary}

Generate a 1-2 sentence transition that:
1. Acknowledges the previous topic is complete
2. Introduces the next topic naturally
3. Keeps the candidate engaged
4. Does NOT reveal scores or detailed feedback

OUTPUT FORMAT (plain text, no JSON):""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # INTERVIEW INTRODUCTION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="interview_introduction",
        version="1.0.0",
        description="Generate the interview introduction message",
        required_vars=["candidate_name", "job_role", "total_pillars", "time_estimate"],
        optional_vars={
            "company_name": "our company",
        },
        template="""Generate a professional interview introduction.

CANDIDATE: {candidate_name}
ROLE: {job_role}
TOPICS TO COVER: {total_pillars}
ESTIMATED TIME: {time_estimate} minutes

Generate a brief, welcoming introduction that:
1. Greets the candidate professionally
2. Explains the interview structure (topics, timing)
3. Sets expectations (no right/wrong, think out loud)
4. Encourages them to ask for clarification if needed

OUTPUT FORMAT (plain text, no JSON):""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # INTERVIEW CONCLUSION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="interview_conclusion",
        version="1.0.0",
        description="Generate the interview conclusion message",
        required_vars=["candidate_name", "completion_status"],
        optional_vars={
            "next_steps": "We will be in touch with next steps.",
        },
        template="""Generate a professional interview conclusion.

CANDIDATE: {candidate_name}
STATUS: {completion_status}

Generate a brief conclusion that:
1. Thanks the candidate for their time
2. Indicates the interview is complete
3. Mentions next steps appropriately
4. Maintains professionalism regardless of performance

OUTPUT FORMAT (plain text, no JSON):""",
    ),
]
