from pydantic import BaseModel, Field
from typing import List

class JDParsingOutput(BaseModel):
    """Output for JD role parsing."""
    role: str = Field(description="The core role title extracted from the JD")
    description: str = Field(description="A brief summary of the role description")

class SkillExtractionOutput(BaseModel):
    """Output for skill extraction."""
    must_have_skills: List[str] = Field(description="List of mandatory technical skills")
    good_to_have: List[str] = Field(description="List of preferred or optional skills")

class CompetencyMappingOutput(BaseModel):
    """Output for competency and tool mapping."""
    experience_range: str = Field(description="Required experience range (e.g., '3-5 years')")
    tools: List[str] = Field(description="List of specific tools, platforms, or libraries")
    competencies: List[str] = Field(description="List of soft skills and core competencies")
