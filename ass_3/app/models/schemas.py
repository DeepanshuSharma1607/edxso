from __future__ import annotations
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
import uuid
import time


class RoleAnalysis(BaseModel):
    role_title: str = ""
    key_responsibilities: List[str] = Field(default_factory=list)
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    technical_competencies: List[str] = Field(default_factory=list)
    behavioural_competencies: List[str] = Field(default_factory=list)
    experience_expectations: str = ""
    important_keywords: List[str] = Field(default_factory=list)
    important_concepts: List[str] = Field(default_factory=list)
    key_qualifications: List[str] = Field(default_factory=list)


class CandidateAnalysis(BaseModel):
    key_skills: List[str] = Field(default_factory=list)
    relevant_experience: List[str] = Field(default_factory=list)
    relevant_projects: List[str] = Field(default_factory=list)
    relevant_achievements: List[str] = Field(default_factory=list)
    strengths_vs_jd: List[str] = Field(default_factory=list)
    missing_skills: List[str] = Field(default_factory=list)
    weak_areas: List[str] = Field(default_factory=list)
    claims_to_probe: List[str] = Field(default_factory=list)
    prep_focus_areas: List[str] = Field(default_factory=list)


class JobFit(BaseModel):
    score: int = 0
    strong_match: List[str] = Field(default_factory=list)
    partial_match: List[str] = Field(default_factory=list)
    missing_or_weak: List[str] = Field(default_factory=list)
    rationale: str = ""


class QAExchange(BaseModel):
    level: Literal["screening", "competency", "deep_dive"]
    question: str
    answer: Optional[str] = None
    answer_quality: Optional[int] = None  # 1-5, set after evaluation
    tags: List[str] = Field(default_factory=list)  # e.g. claim probed, weak area
    timestamp: float = Field(default_factory=time.time)


class LevelFeedback(BaseModel):
    questions_answered: int = 0
    average_quality: float = 0.0
    feedback: str = ""


class PerformanceReport(BaseModel):
    overall_score: int = 0  # 0-100, derived from per-answer quality scores
    readiness_label: str = ""  # e.g. "Not Ready", "Needs Practice", "Interview Ready", "Strong Candidate"
    summary: str = ""
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    per_level_feedback: dict[str, LevelFeedback] = Field(default_factory=dict)
    improvement_plan: List[str] = Field(default_factory=list)
    generated_at: float = Field(default_factory=time.time)


class Session(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    jd_text: str = ""
    resume_text: str = ""
    role_analysis: Optional[RoleAnalysis] = None
    candidate_analysis: Optional[CandidateAnalysis] = None
    job_fit: Optional[JobFit] = None
    current_level: Literal["screening", "competency", "deep_dive", "done"] = "screening"
    transcript: List[QAExchange] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)
    interview_started_at: Optional[float] = None
    ended_reason: Optional[Literal["completed", "user_stopped", "time_limit"]] = None
    performance_report: Optional[PerformanceReport] = None
