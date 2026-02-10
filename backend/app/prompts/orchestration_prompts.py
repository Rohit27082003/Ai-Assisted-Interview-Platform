from langchain_core.prompts import ChatPromptTemplate

# ═══════════════════════════════════════════════════════════════════════════
# PILLAR TRANSITION
# ═══════════════════════════════════════════════════════════════════════════

PILLAR_TRANSITION_PROMPT = ChatPromptTemplate.from_template(
    """Generate a brief, professional transition message.

PREVIOUS TOPIC: {previous_pillar}
NEXT TOPIC: {next_pillar}
CANDIDATE: {candidate_name}
PREVIOUS PERFORMANCE: {previous_performance_summary}

Generate a 1-2 sentence transition that:
1. Acknowledges the previous topic is complete
2. Introduces the next topic naturally
3. Keeps the candidate engaged
4. Does NOT reveal scores or detailed feedback

OUTPUT FORMAT (plain text, no JSON):"""
)


# ═══════════════════════════════════════════════════════════════════════════
# INTERVIEW INTRODUCTION
# ═══════════════════════════════════════════════════════════════════════════

INTERVIEW_INTRODUCTION_PROMPT = ChatPromptTemplate.from_template(
    """Generate a professional interview introduction.

CANDIDATE: {candidate_name}
ROLE: {job_role}
TOPICS TO COVER: {total_pillars}
ESTIMATED TIME: {time_estimate} minutes

Generate a brief, welcoming introduction that:
1. Greets the candidate professionally
2. Explains the interview structure (topics, timing)
3. Sets expectations (no right/wrong, think out loud)
4. Encourages them to ask for clarification if needed

OUTPUT FORMAT (plain text, no JSON):"""
)


# ═══════════════════════════════════════════════════════════════════════════
# INTERVIEW CONCLUSION
# ═══════════════════════════════════════════════════════════════════════════

INTERVIEW_CONCLUSION_PROMPT = ChatPromptTemplate.from_template(
    """Generate a professional interview conclusion.

CANDIDATE: {candidate_name}
STATUS: {completion_status}

Generate a brief conclusion that:
1. Thanks the candidate for their time
2. Indicates the interview is complete
3. Mentions next steps appropriately
4. Maintains professionalism regardless of performance

OUTPUT FORMAT (plain text, no JSON):"""
)
