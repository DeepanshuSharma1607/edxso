import json
from app.services.llm import llm_json
from app.models.schemas import RoleAnalysis, CandidateAnalysis, JobFit
from app.prompts.analysis_prompts import (
    ROLE_ANALYSIS_SYSTEM,
    ROLE_ANALYSIS_USER_TEMPLATE,
    CANDIDATE_ANALYSIS_SYSTEM,
    CANDIDATE_ANALYSIS_USER_TEMPLATE,
    JOB_FIT_SYSTEM,
    JOB_FIT_USER_TEMPLATE,
)


async def analyse_role(jd_text: str) -> RoleAnalysis:
    data = await llm_json(
        ROLE_ANALYSIS_SYSTEM,
        ROLE_ANALYSIS_USER_TEMPLATE.format(jd_text=jd_text),
    )
    return RoleAnalysis(**data)


async def analyse_candidate(resume_text: str, role_analysis: RoleAnalysis) -> CandidateAnalysis:
    data = await llm_json(
        CANDIDATE_ANALYSIS_SYSTEM,
        CANDIDATE_ANALYSIS_USER_TEMPLATE.format(
            role_analysis_json=role_analysis.model_dump_json(),
            resume_text=resume_text,
        ),
    )
    return CandidateAnalysis(**data)


async def compute_job_fit(role_analysis: RoleAnalysis, candidate_analysis: CandidateAnalysis) -> JobFit:
    data = await llm_json(
        JOB_FIT_SYSTEM,
        JOB_FIT_USER_TEMPLATE.format(
            role_analysis_json=role_analysis.model_dump_json(),
            candidate_analysis_json=candidate_analysis.model_dump_json(),
        ),
    )
    return JobFit(**data)
