from pydantic import BaseModel, Field
from typing import List
from app.schemas.schemas import FocusArea

class FocusAreaListOutput(BaseModel):
    """Output schema for focus area selection."""
    focus_areas: List[FocusArea] = Field(
        description="List of selected focus areas (4-5 items)",
        min_items=3,
        max_items=6
    )
