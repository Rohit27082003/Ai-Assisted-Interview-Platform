"""Graph 1 — JD Intelligence Graph.

Nodes:
  - jd_parser: Parse raw JD text
  - skill_extractor: Extract must-have and nice-to-have skills
  - competency_mapper: Map competencies and tools
  - classifier: Classify mandatory vs preferred requirements

Returns typed JDObject, stores in Postgres + embeds in Chroma.
"""

from typing import TypedDict, List
from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, END

from app.core.llm import get_llm, get_structured_llm
from app.schemas.schemas import JDObject
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Graph State ───────────────────────────────────────────────────

class JDGraphState(TypedDict):
    raw_text: str
    title: str
    parsed_role: str
    must_have_skills: List[str]
    good_to_have: List[str]
    experience_range: str
    tools: List[str]
    competencies: List[str]
    jd_object: dict


# ── Node Functions ────────────────────────────────────────────────

async def jd_parser_node(state: JDGraphState) -> JDGraphState:
    """Parse the JD and extract the role description."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an expert HR job description analyst.
Parse the following job description and extract the core role title and description.
Return ONLY a JSON object with keys: "role" (string), "description" (string).
Do not include any markdown formatting or extra text."""),
        ("human", "{jd_text}"),
    ])
    chain = prompt | llm
    response = await chain.ainvoke({"jd_text": state["raw_text"]})
    import json
    try:
        parsed = json.loads(response.content)
        state["parsed_role"] = parsed.get("role", state["title"])
    except (json.JSONDecodeError, AttributeError):
        state["parsed_role"] = state["title"]
    logger.info(f"JD parsed: role={state['parsed_role']}")
    return state


async def skill_extractor_node(state: JDGraphState) -> JDGraphState:
    """Extract must-have and good-to-have skills from the JD."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are a technical skills extraction specialist.
From the job description below, extract:
1. must_have_skills: Skills that are explicitly required or mandatory
2. good_to_have: Skills that are preferred, optional, or "nice to have"

Return ONLY a JSON object with keys: "must_have_skills" (list of strings), "good_to_have" (list of strings).
Be specific with skill names. Do not include any markdown formatting."""),
        ("human", "{jd_text}"),
    ])
    chain = prompt | llm
    response = await chain.ainvoke({"jd_text": state["raw_text"]})
    import json
    try:
        parsed = json.loads(response.content)
        state["must_have_skills"] = parsed.get("must_have_skills", [])
        state["good_to_have"] = parsed.get("good_to_have", [])
    except (json.JSONDecodeError, AttributeError):
        state["must_have_skills"] = []
        state["good_to_have"] = []
    logger.info(f"Skills extracted: must_have={len(state['must_have_skills'])}, good_to_have={len(state['good_to_have'])}")
    return state


async def competency_mapper_node(state: JDGraphState) -> JDGraphState:
    """Map competencies, tools, and experience requirements."""
    llm = get_llm()
    prompt = ChatPromptTemplate.from_messages([
        ("system", """You are an HR competency mapping expert.
From the job description, extract:
1. experience_range: e.g., "3-5 years" or "5+ years"
2. tools: Specific tools, frameworks, platforms mentioned
3. competencies: Soft skills, leadership qualities, domain competencies

Return ONLY a JSON with keys: "experience_range" (string), "tools" (list of strings), "competencies" (list of strings).
Do not include any markdown formatting."""),
        ("human", "{jd_text}"),
    ])
    chain = prompt | llm
    response = await chain.ainvoke({"jd_text": state["raw_text"]})
    import json
    try:
        parsed = json.loads(response.content)
        state["experience_range"] = parsed.get("experience_range", "")
        state["tools"] = parsed.get("tools", [])
        state["competencies"] = parsed.get("competencies", [])
    except (json.JSONDecodeError, AttributeError):
        state["experience_range"] = ""
        state["tools"] = []
        state["competencies"] = []
    logger.info(f"Competencies mapped: tools={len(state['tools'])}, competencies={len(state['competencies'])}")
    return state


async def classifier_node(state: JDGraphState) -> JDGraphState:
    """Assemble the final typed JDObject."""
    jd_obj = JDObject(
        role=state.get("parsed_role", state["title"]),
        must_have_skills=state.get("must_have_skills", []),
        good_to_have=state.get("good_to_have", []),
        experience_range=state.get("experience_range", ""),
        tools=state.get("tools", []),
        competencies=state.get("competencies", []),
    )
    state["jd_object"] = jd_obj.model_dump()
    logger.info(f"JD Intelligence complete: {jd_obj.role}")
    return state


# ── Build Graph ───────────────────────────────────────────────────

def build_jd_intelligence_graph() -> StateGraph:
    """Build and compile the JD Intelligence Graph."""
    graph = StateGraph(JDGraphState)

    graph.add_node("jd_parser", jd_parser_node)
    graph.add_node("skill_extractor", skill_extractor_node)
    graph.add_node("competency_mapper", competency_mapper_node)
    graph.add_node("classifier", classifier_node)

    graph.set_entry_point("jd_parser")
    graph.add_edge("jd_parser", "skill_extractor")
    graph.add_edge("skill_extractor", "competency_mapper")
    graph.add_edge("competency_mapper", "classifier")
    graph.add_edge("classifier", END)

    return graph.compile()
