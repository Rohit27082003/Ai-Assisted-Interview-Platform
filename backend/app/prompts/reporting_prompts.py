"""
Reporting Prompts - Final report generation

These prompts are used to generate comprehensive interview reports
including performance analysis, recommendations, and executive summaries.
"""

from .registry import PromptTemplate


REPORTING_PROMPTS = [
    # ═══════════════════════════════════════════════════════════════════════════
    # PERFORMANCE ANALYSIS
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="performance_analysis",
        version="2.0.0",
        description="Analyze overall performance to identify strengths and weaknesses",
        required_vars=["evaluations_json", "pillar_scores", "job_role"],
        optional_vars={
            "job_requirements": "{}",
            "cheating_flags": "[]",
        },
        output_schema="PerformanceAnalysisOutput",
        template="""Analyze this candidate's interview performance comprehensively.

JOB ROLE: {job_role}
JOB REQUIREMENTS: {job_requirements}

PILLAR SCORES:
{pillar_scores}

DETAILED EVALUATIONS:
{evaluations_json}

CHEATING FLAGS:
{cheating_flags}

INSTRUCTIONS:
1. Identify 3-5 distinct STRENGTHS with supporting evidence
2. Identify 3-5 distinct WEAKNESSES with supporting evidence
3. Note standout and concerning answers
4. Assess communication and problem-solving approach
5. Flag any integrity concerns

STRENGTH/WEAKNESS CRITERIA:
- Must be specific (not "good at coding")
- Must have evidence from interview
- Must be relevant to the job role
- Rate impact: high/medium/low

OUTPUT FORMAT (JSON only, no markdown):
{{
    "strengths": [
        {{
            "area": "Specific skill/competency",
            "observation": "What was demonstrated",
            "evidence": ["Q3: specific quote/behavior", "Q7: another example"],
            "impact": "high|medium|low"
        }}
    ],
    "weaknesses": [
        {{
            "area": "Specific skill/competency",
            "observation": "What was lacking",
            "evidence": ["Q5: struggled with...", "Q9: couldn't explain..."],
            "impact": "high|medium|low"
        }}
    ],
    "performance_summary": "2-3 sentence overall summary",
    "skill_profile": {{
        "skill_name": 0.0-100.0
    }},
    "standout_answers": ["Q3: Why it was notable"],
    "concerning_answers": ["Q8: Why it was concerning"],
    "communication_quality": "excellent|good|adequate|needs_improvement",
    "problem_solving_approach": "systematic|intuitive|scattered|methodical",
    "integrity_concerns": true|false,
    "integrity_notes": "Explanation if concerns exist, else null"
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # HIRING RECOMMENDATION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="hiring_recommendation",
        version="2.0.0",
        description="Generate a hiring recommendation with rationale",
        required_vars=[
            "performance_analysis",
            "overall_score",
            "job_role",
            "job_requirements",
        ],
        optional_vars={
            "cheating_assessment": "clean",
            "team_context": "",
        },
        output_schema="RecommendationOutput",
        template="""Generate a hiring recommendation based on interview performance.

JOB ROLE: {job_role}
JOB REQUIREMENTS: {job_requirements}

OVERALL SCORE: {overall_score}/100

PERFORMANCE ANALYSIS:
{performance_analysis}

INTEGRITY ASSESSMENT: {cheating_assessment}

TEAM CONTEXT:
{team_context}

RECOMMENDATION FRAMEWORK:

STRONG_HIRE (85+):
- Exceeds most requirements
- Strong in critical areas
- No significant concerns
- Would strengthen the team

HIRE (70-84):
- Meets requirements
- Acceptable gaps that can be addressed
- Overall positive impression
- Good culture fit indicators

BORDERLINE (55-69):
- Meets some requirements
- Significant gaps but addressable
- Mixed signals
- May depend on team needs

NO_HIRE (40-54):
- Missing key requirements
- Fundamental gaps
- Concerns outweigh positives

STRONG_NO_HIRE (<40 or integrity issues):
- Does not meet requirements
- Serious concerns
- Integrity violations

OUTPUT FORMAT (JSON only, no markdown):
{{
    "recommendation": "strong_hire|hire|borderline|no_hire|strong_no_hire",
    "confidence": 0.0-1.0,
    "primary_reasons": ["Reason 1", "Reason 2", "Reason 3"],
    "concerns": ["Concern even if recommending hire"],
    "role_fit_score": 0.0-100.0,
    "role_fit_rationale": "Explanation of role fit",
    "growth_potential": "high|moderate|limited",
    "suggested_level": "junior|mid|senior|staff|null",
    "conditional_factors": ["Factor that might change recommendation"]
}}""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # EXECUTIVE SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="executive_summary",
        version="1.0.0",
        description="Generate an executive summary for hiring managers",
        required_vars=[
            "candidate_name",
            "job_role",
            "recommendation",
            "strengths",
            "weaknesses",
            "overall_score",
        ],
        optional_vars={
            "interview_duration": "45 minutes",
            "pillars_covered": "4",
        },
        template="""Write an executive summary for a hiring manager.

CANDIDATE: {candidate_name}
ROLE: {job_role}
RECOMMENDATION: {recommendation}
OVERALL SCORE: {overall_score}/100
INTERVIEW DURATION: {interview_duration}
TOPICS COVERED: {pillars_covered}

KEY STRENGTHS:
{strengths}

KEY WEAKNESSES:
{weaknesses}

INSTRUCTIONS:
Write a 2-3 paragraph executive summary that:
1. Opens with the recommendation and confidence
2. Summarizes key strengths that support hiring
3. Acknowledges concerns and their significance
4. Concludes with suggested next steps

TONE:
- Professional and objective
- Evidence-based, not vague
- Actionable for the hiring manager
- Neither overselling nor underselling

OUTPUT FORMAT (plain text, 200-400 words):""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # DETAILED FEEDBACK BY PILLAR
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="pillar_feedback",
        version="1.0.0",
        description="Generate detailed feedback for a specific pillar",
        required_vars=["pillar_name", "pillar_score", "questions_and_answers"],
        optional_vars={
            "job_requirements_for_pillar": "",
        },
        template="""Generate detailed feedback for this interview topic.

TOPIC/PILLAR: {pillar_name}
PILLAR SCORE: {pillar_score}/100
RELEVANT JOB REQUIREMENTS: {job_requirements_for_pillar}

QUESTIONS AND ANSWERS:
{questions_and_answers}

INSTRUCTIONS:
Provide detailed feedback including:
1. Overall assessment of knowledge in this area
2. Specific examples of good responses
3. Specific gaps or areas of confusion
4. How this relates to job requirements
5. Development recommendations if hired

OUTPUT FORMAT (2-3 paragraphs, 150-250 words):""",
    ),
    # ═══════════════════════════════════════════════════════════════════════════
    # FINAL REPORT COMPILATION
    # ═══════════════════════════════════════════════════════════════════════════
    PromptTemplate(
        name="compile_final_report",
        version="1.0.0",
        description="Compile all analysis into final structured report",
        required_vars=[
            "candidate_name",
            "job_title",
            "interview_date",
            "interview_duration",
            "overall_score",
            "recommendation",
            "pillar_scores",
            "strengths",
            "weaknesses",
            "executive_summary",
            "detailed_feedback",
        ],
        optional_vars={
            "cheating_flags": "[]",
            "questions_asked": "15",
            "follow_ups_asked": "5",
            "completion_status": "completed",
        },
        output_schema="FinalReportOutput",
        template="""Compile the final interview report from all analysis components.

CANDIDATE: {candidate_name}
JOB TITLE: {job_title}
DATE: {interview_date}
DURATION: {interview_duration} minutes

OVERALL SCORE: {overall_score}/100
RECOMMENDATION: {recommendation}

PILLAR SCORES:
{pillar_scores}

STRENGTHS:
{strengths}

WEAKNESSES:
{weaknesses}

EXECUTIVE SUMMARY:
{executive_summary}

DETAILED FEEDBACK:
{detailed_feedback}

CHEATING FLAGS: {cheating_flags}
QUESTIONS ASKED: {questions_asked}
FOLLOW-UPS: {follow_ups_asked}
COMPLETION STATUS: {completion_status}

OUTPUT FORMAT (JSON only, no markdown):
{{
    "candidate_name": "{candidate_name}",
    "job_title": "{job_title}",
    "interview_date": "{interview_date}",
    "interview_duration_minutes": {interview_duration},
    "final_score": {overall_score},
    "adjusted_score": <score after any deductions>,
    "recommendation": "{recommendation}",
    "recommendation_confidence": 0.0-1.0,
    "pillar_scores": {pillar_scores},
    "dimension_scores": {{
        "correctness": 0.0-100.0,
        "depth": 0.0-100.0,
        "reasoning": 0.0-100.0,
        "clarity": 0.0-100.0
    }},
    "strengths": [formatted strengths],
    "weaknesses": [formatted weaknesses],
    "executive_summary": "{executive_summary}",
    "detailed_feedback": {detailed_feedback},
    "cheating_flags": {cheating_flags},
    "integrity_assessment": "clean|minor_concerns|major_concerns|disqualified",
    "questions_asked": {questions_asked},
    "follow_ups_asked": {follow_ups_asked},
    "pillars_covered": <count>,
    "completion_status": "{completion_status}",
    "suggested_next_steps": ["step1", "step2"]
}}""",
    ),
]
