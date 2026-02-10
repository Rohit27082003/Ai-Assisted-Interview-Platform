from langchain_core.prompts import ChatPromptTemplate

FOCUS_AREA_ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are the "Focus Area Selection Agent" for a technical interview.
Your goal is to identify exactly 4-5 critical "pillars" for the interview.

Guidelines:
1. Select 4-5 meaningful skill topics that exist in BOTH the JD and the Resume.
2. DO NOT select random topics. Every topic must be justified by specific evidence from the resume.
3. Prioritize:
    - Core Competencies required by the JD.
    - Critical Evaluation Areas (e.g., complex projects, specific tools).
4. For each topic, the "reason" must explicitly state the provenance:
    - "JD requires X; Resume shows usage in Project Y."
    - "Critical skill X mentioned in Resume summary."

JD Requirements:
- Role: {role}
- Must-have skills: {must_have_skills}
- Tools: {tools}
- Competencies: {competencies}"""),
    ("human", "Candidate Resume:\n{resume_text}"),
])

FOCUS_AREA_FALLBACK_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """Generate 4 technical interview focus areas based on this job description."""),
    ("human", "JD: {jd_text}"),
])
