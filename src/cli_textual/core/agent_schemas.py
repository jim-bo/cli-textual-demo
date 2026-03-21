from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field

class StudyResolution(BaseModel):
    """Output schema for the study resolver sub-agent."""
    study_id: str = Field(description="The unique identifier for the study (e.g., 'brca_tcga')")
    study_name: str = Field(description="The human-readable name of the study")
    confidence: float = Field(description="Confidence score (0.0 to 1.0) that this is the correct study")
    clarification_needed: Optional[str] = Field(
        None, description="A question to ask the user if confidence is low or disambiguation is needed"
    )

class ValidationResult(BaseModel):
    """Output schema for the parameter validator sub-agent."""
    is_valid: bool = Field(description="Whether the requested attributes are available in the chosen study")
    available_attributes: List[str] = Field(description="The list of attributes found and validated")
    missing_attributes: List[str] = Field(description="The list of attributes requested but not found")
    clarification_needed: Optional[str] = Field(
        None, description="A question to ask the user if they should proceed without missing attributes"
    )

class GeneratedLink(BaseModel):
    """Output schema for the link generator sub-agent."""
    url: str = Field(description="The full cBioPortal URL for the generated query")
    explanation: str = Field(description="A concise summary of what this link provides to the user")
