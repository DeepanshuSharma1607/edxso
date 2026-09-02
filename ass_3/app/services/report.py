"""
Phase 7 — evaluation & report generation.

Numeric scores (per-level averages, overall score, readiness label) are
computed deterministically here from each QAExchange's answer_quality — never
asked of the LLM, since an LLM re-deriving an average from a transcript it's
also reading is a place for silent arithmetic drift. The LLM's job is purely
the narrative: summary, strengths/weaknesses, per-level feedback text, and an
improvement plan — all grounded in the transcript and the computed stats.
"""
from app.models.schemas import Session, LevelFeedback, PerformanceReport
from app.services.llm import llm_json
from app.services.interview import LEVEL_ORDER, _format_transcript
from app.prompts.report_prompts import REPORT_SYSTEM, REPORT_USER_TEMPLATE

_READINESS_BANDS = [
    (80, "Strong Candidate"),
    (60, "Interview Ready"),
    (40, "Needs Practice"),
    (0, "Not Ready"),
]


def _readiness_label(score: int) -> str:
    for threshold, label in _READINESS_BANDS:
        if score >= threshold:
            return label
    return _READINESS_BANDS[-1][1]


def _compute_level_stats(session: Session) -> dict[str, LevelFeedback]:
    stats: dict[str, LevelFeedback] = {}
    for level in LEVEL_ORDER:
        qualities = [
            qa.answer_quality
            for qa in session.transcript
            if qa.level == level and qa.answer is not None and qa.answer_quality is not None
        ]
        answered = sum(1 for qa in session.transcript if qa.level == level and qa.answer is not None)
        avg = round(sum(qualities) / len(qualities), 2) if qualities else 0.0
        stats[level] = LevelFeedback(questions_answered=answered, average_quality=avg, feedback="")
    return stats


def _compute_overall_score(level_stats: dict[str, LevelFeedback]) -> int:
    qualities = [(lf.average_quality, lf.questions_answered) for lf in level_stats.values() if lf.questions_answered > 0]
    if not qualities:
        return 0
    total_questions = sum(count for _, count in qualities)
    weighted_avg = sum(avg * count for avg, count in qualities) / total_questions
    return round((weighted_avg / 5.0) * 100)


async def generate_report(session: Session) -> PerformanceReport:
    if not session.transcript:
        raise ValueError("Interview has not started — nothing to report on.")
    answered_count = sum(1 for qa in session.transcript if qa.answer is not None)
    if answered_count == 0:
        raise ValueError("No questions were answered — nothing to report on.")

    level_stats = _compute_level_stats(session)
    overall_score = _compute_overall_score(level_stats)

    data = await llm_json(
        REPORT_SYSTEM,
        REPORT_USER_TEMPLATE.format(
            role_analysis_json=session.role_analysis.model_dump_json() if session.role_analysis else "{}",
            candidate_analysis_json=session.candidate_analysis.model_dump_json() if session.candidate_analysis else "{}",
            job_fit_json=session.job_fit.model_dump_json() if session.job_fit else "{}",
            ended_reason=session.ended_reason or "unknown",
            level_stats_json="\n".join(f"{lvl}: {lf.model_dump()}" for lvl, lf in level_stats.items()),
            transcript_text=_format_transcript(session),
        ),
    )

    per_level_feedback_text = data.get("per_level_feedback", {}) or {}
    for level, lf in level_stats.items():
        lf.feedback = str(per_level_feedback_text.get(level, "") or "")

    return PerformanceReport(
        overall_score=overall_score,
        readiness_label=_readiness_label(overall_score),
        summary=str(data.get("summary", "")),
        strengths=list(data.get("strengths", [])),
        weaknesses=list(data.get("weaknesses", [])),
        per_level_feedback=level_stats,
        improvement_plan=list(data.get("improvement_plan", [])),
    )
