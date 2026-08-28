"""
Structured scholarship schema.

Design rule (anti-hallucination): every field is Optional[str]. When the
extractor (rule-based or LLM) cannot find direct textual support for a
field in the source content, it MUST be set to the literal string
"NOT_SPECIFIED" rather than guessed. `evidence` carries a parallel map of
field -> exact supporting text so every important value is traceable back
to the source.
"""
from typing import Optional, Dict
from pydantic import BaseModel, Field, ConfigDict

NOT_SPECIFIED = "NOT_SPECIFIED"


class ScholarshipRecord(BaseModel):
    name: str
    provider: str
    amount: str = NOT_SPECIFIED
    benefit_type: str = NOT_SPECIFIED
    eligibility: str = NOT_SPECIFIED          # may hold a JSON string of tiered rules
    academic_requirements: str = NOT_SPECIFIED
    course_level: str = NOT_SPECIFIED
    income_criteria: str = NOT_SPECIFIED
    age_criteria: str = NOT_SPECIFIED
    gender_criteria: str = NOT_SPECIFIED
    category_criteria: str = NOT_SPECIFIED
    domicile: str = NOT_SPECIFIED
    institution_requirements: str = NOT_SPECIFIED
    opening_date: str = NOT_SPECIFIED          # ISO yyyy-mm-dd or NOT_SPECIFIED
    closing_date: str = NOT_SPECIFIED
    documents_required: str = NOT_SPECIFIED
    selection_process: str = NOT_SPECIFIED
    renewal_requirements: str = NOT_SPECIFIED
    application_url: str = NOT_SPECIFIED
    official_source_url: str
    source_type: str
    discovery_url: Optional[str] = None

    # evidence[field_name] = verbatim (or lightly trimmed) supporting text
    evidence: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")
