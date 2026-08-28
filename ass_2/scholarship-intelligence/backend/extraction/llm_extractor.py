"""
LLM-backed structured extractor (Mistral).

Used only for messy/unstructured webpage text where a deterministic parser
(rule_extractor.py) is not viable. The LLM's ONLY job is to reshape text
into JSON matching ScholarshipRecord -- it never invents values, and it
must copy verbatim evidence for every field it fills in. Confidence
scoring is calculated separately and deterministically in
verification/confidence.py; the LLM never assigns or is asked for a score.
"""
import os
import json
import re
from typing import Optional
from backend.extraction.schemas import ScholarshipRecord, NOT_SPECIFIED

SYSTEM_PROMPT = """You are a strict information-extraction engine for an Indian \
scholarship database. You will be given raw text scraped from a webpage about \
one scholarship. Extract ONLY facts that are explicitly stated in the text.

Rules (violating these is a critical failure):
1. Never invent, estimate, or infer a value that is not explicitly present in the text.
2. If a field is not explicitly stated, its value MUST be exactly "NOT_SPECIFIED".
3. For every field you DO fill in (other than NOT_SPECIFIED), copy the exact \
supporting sentence/phrase from the source text into the matching key of "evidence".
4. Output ONLY a single JSON object, no prose, no markdown fences.
5. Use this exact JSON schema (all keys required):
{
  "name": str, "provider": str, "amount": str, "benefit_type": str,
  "eligibility": str, "academic_requirements": str, "course_level": str,
  "income_criteria": str, "age_criteria": str, "gender_criteria": str,
  "category_criteria": str, "domicile": str, "institution_requirements": str,
  "opening_date": str, "closing_date": str, "documents_required": str,
  "selection_process": str, "renewal_requirements": str, "application_url": str,
  "evidence": {"<field_name>": "<verbatim supporting text>"}
}
"""


def _get_client():
    from mistralai import Mistral
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise RuntimeError("MISTRAL_API_KEY not set in environment/.env")
    return Mistral(api_key=api_key)


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def extract_with_llm(
    raw_text: str,
    official_source_url: str,
    source_type: str,
    discovery_url: Optional[str] = None,
    model: str = "mistral-small-latest",
) -> ScholarshipRecord:
    """Call Mistral to turn raw scraped text into a ScholarshipRecord.

    Requires network access to api.mistral.ai and a valid MISTRAL_API_KEY.
    Raises on any malformed/missing-JSON response rather than silently
    guessing -- a failed extraction should surface, not fabricate data.
    """
    client = _get_client()
    resp = client.chat.complete(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"OFFICIAL SOURCE: {official_source_url}\n\nRAW TEXT:\n{raw_text}"},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    content = _strip_fences(resp.choices[0].message.content)
    data = json.loads(content)

    data["official_source_url"] = official_source_url
    data["source_type"] = source_type
    data["discovery_url"] = discovery_url
    for k, v in list(data.items()):
        if v in (None, ""):
            data[k] = NOT_SPECIFIED
    return ScholarshipRecord(**data)
