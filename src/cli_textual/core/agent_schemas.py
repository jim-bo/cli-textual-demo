from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel, Field

class IntentResolution(BaseModel):
    """Output schema for the intent resolver sub-agent."""
    target_id: str = Field(description="The unique identifier for the resolved subject (e.g., 'brca_tcga')")
    target_name: str = Field(description="The human-readable name of the subject")
    confidence: float = Field(description="Confidence score (0.0 to 1.0) that this is the correct subject")
    clarification_needed: Optional[str] = Field(
        None, description="A question to ask the user if confidence is low or disambiguation is needed"
    )

class ValidationResult(BaseModel):
    """Output schema for the data validator sub-agent."""
    is_valid: bool = Field(description="Whether the requested details are available for the chosen subject")
    available_attributes: List[str] = Field(description="The list of details found and validated")
    missing_attributes: List[str] = Field(description="The list of details requested but not found")
    clarification_needed: Optional[str] = Field(
        None, description="A question to ask the user if they should proceed without missing details"
    )

class StructuredResult(BaseModel):
    """Output schema for the result generator sub-agent."""
    output_data: str = Field(description="The final structured output (URL, summary, etc.)")
    explanation: str = Field(description="A concise summary of what this result provides to the user")
