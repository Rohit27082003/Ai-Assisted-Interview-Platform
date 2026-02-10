from langchain_core.prompts import ChatPromptTemplate

JD_PARSER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert HR job description analyst.
Parse the following job description and extract the core role title and description."""),
    ("human", "{jd_text}"),
])

SKILL_EXTRACTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a technical skills extraction specialist.
From the job description below, extract:
1. must_have_skills: Skills that are explicitly required or mandatory
2. good_to_have: Skills that are preferred, optional, or "nice to have"

Be specific with skill names."""),
    ("human", "{jd_text}"),
])

COMPETENCY_MAPPING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an HR competency mapping expert.
From the job description, extract:
1. experience_range: e.g., "3-5 years" or "5+ years"
2. tools: Specific tools, frameworks, platforms mentioned
3. competencies: Soft skills, leadership qualities, domain competencies"""),
    ("human", "{jd_text}"),
])
