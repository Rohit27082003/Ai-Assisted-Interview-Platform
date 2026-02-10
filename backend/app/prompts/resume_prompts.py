"""
Resume Intelligence Prompts

These prompts are used by the resume_intelligence graph to:
1. Parse resume content into structured data
2. Analyze candidate fit against JD
3. Detect exaggerated claims
"""

from langchain_core.prompts import ChatPromptTemplate

# ═══════════════════════════════════════════════════════════════════════════
# RESUME PARSING
# ═══════════════════════════════════════════════════════════════════════════

RESUME_PARSER_PROMPT = ChatPromptTemplate.from_template(
    """You are an expert technical recruiter and resume analyst.

CONTEXT:
Today's date is: {current_date}

Use this date to correctly interpret all dates on the resume. All employment dates, education dates, and project dates should be evaluated relative to this date.

RESUME TEXT:
{resume_text}

INSTRUCTIONS:
1. Extract SKILLS: Technical skills, languages, frameworks.
2. Extract PROJECTS: Brief description of key projects.
3. Calculate EXPERIENCE:
   - Sum up full-time professional experience in years.
   - EXCLUDE internships unless they are > 6 months and highly relevant.
   - EXCLUDE concurrent roles (don't double count time).
   - Use the current date above to accurately calculate years of experience.
4. Identify CLAIMS: Extract specific measurable claims (e.g., "Improved latency by 50%", "Scaled to 1M users").
5. Summarize: Create a professional summary."""
)


# ═══════════════════════════════════════════════════════════════════════════
# SEMANTIC MATCHING & SCORING
# ═══════════════════════════════════════════════════════════════════════════

RESUME_ANALYSIS_PROMPT = ChatPromptTemplate.from_template(
    """You are a strict Senior Technical Hiring Manager. Evaluate this candidate for the specific role.

CONTEXT:
Today's date is: {current_date}

Use this date to correctly interpret all dates on the resume. All employment dates, education dates, and project dates should be evaluated relative to this date to accurately assess years of experience and recency of work.

JOB DESCRIPTION (JD):
Role: {role}
Must-Have Skills: {must_have_skills}
Good-to-Have Skills: {good_to_have}
Experience Range: {experience_range}
Tools: {tools}

CANDIDATE RESUME:
{resume_text}

EVALUATION CRITERIA:
1. SKILLS MATCH (40%):
   - Do they have the REQUIRED skills?
   - specific frameworks/languages mentioned in JD?
   - Penalty for missing "Must-Haves".

2. PROJECT RELEVANCE (30%):
   - Are their projects similar in scale/domain to the JD?
   - Do they show "hands-on" experience vs just "knowledge of"?

3. EXPERIENCE FIT (20%):
   - Do they meet the minimum years?
   - Is the experience QUALITY (e.g., leading teams vs junior dev)?
   - Calculate years correctly using the current date provided above.

4. CLAIM VALIDITY & SIGNAL:
   - Do claims seem realistic?
   - Is there evidence (metrics, specific links)?
   - Detect "Keyword Stuffing" (listing skills without context).

CRITICAL RULES:
- Be skeptical. Candidates often exaggerate.
- Look for EVIDENCE of skills, not just the word.
- If they lack a MUST-HAVE skill, the score should be low (<50).
- Use the current date to accurately calculate experience duration."""
)
