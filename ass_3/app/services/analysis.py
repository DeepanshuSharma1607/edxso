from pydantic import ValidationError
from app.services.llm import llm_json, LLMServiceError, as_int
from app.models.schemas import RoleAnalysis, CandidateAnalysis, JobFit
from app.prompts.analysis_prompts import (
    ROLE_ANALYSIS_SYSTEM,
    ROLE_ANALYSIS_USER_TEMPLATE,
    CANDIDATE_ANALYSIS_SYSTEM,
    CANDIDATE_ANALYSIS_USER_TEMPLATE,
    JOB_FIT_SYSTEM,
    JOB_FIT_USER_TEMPLATE,
)


def _build(model, data: dict):
    try:
        return model(**data)
    except ValidationError as e:
        raise LLMServiceError(f"Gemini returned an unexpected {model.__name__} shape: {e}") from e


async def analyse_role(jd_text: str) -> RoleAnalysis:
    data = await llm_json(
        ROLE_ANALYSIS_SYSTEM,
        ROLE_ANALYSIS_USER_TEMPLATE.format(jd_text=jd_text),
    )
    return _build(RoleAnalysis, data)


async def analyse_candidate(resume_text: str, role_analysis: RoleAnalysis) -> CandidateAnalysis:
    data = await llm_json(
        CANDIDATE_ANALYSIS_SYSTEM,
        CANDIDATE_ANALYSIS_USER_TEMPLATE.format(
            role_analysis_json=role_analysis.model_dump_json(),
            resume_text=resume_text,
        ),
    )
    return _build(CandidateAnalysis, data)


async def compute_job_fit(role_analysis: RoleAnalysis, candidate_analysis: CandidateAnalysis) -> JobFit:
    data = await llm_json(
        JOB_FIT_SYSTEM,
        JOB_FIT_USER_TEMPLATE.format(
            role_analysis_json=role_analysis.model_dump_json(),
            candidate_analysis_json=candidate_analysis.model_dump_json(),
        ),
    )
    data["score"] = as_int(data.get("score"), 0, 0, 100)
    return _build(JobFit, data)
