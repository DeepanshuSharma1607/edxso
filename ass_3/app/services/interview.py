"""
Interview orchestration. This is the state machine described in the spec:
screening -> competency -> deep_dive -> done, with adaptive difficulty and
follow-up questions driven by the LLM's evaluation of each answer.

Three ways an interview can end besides the adaptive engine finishing
naturally on its own:
  - the candidate says a stop phrase ("stop the interview", etc.) in a typed
    or voice answer
  - the 10-minute wall-clock cap is hit
  - the "Stop Interview" button calls stop_interview() directly (no answer
    submission involved)
All three skip the LLM call entirely — no evaluation needed once we know
we're ending the interview — and record why via session.ended_reason.
"""
import re
import time
from typing import Optional

from app.models.schemas import Session, QAExchange
from app.services.llm import llm_json
from app.prompts.interview_prompts import (
    LEVEL_INSTRUCTIONS,
    OPENING_QUESTION_SYSTEM,
    OPENING_QUESTION_USER_TEMPLATE,
    NEXT_TURN_SYSTEM,
    NEXT_TURN_USER_TEMPLATE,
)

# Guardrails so a chatty LLM can't loop forever or bail after one question.
MIN_QUESTIONS_PER_LEVEL = {"screening": 2, "competency": 3, "deep_dive": 3}
MAX_QUESTIONS_PER_LEVEL = {"screening": 4, "competency": 5, "deep_dive": 5}

LEVEL_ORDER = ["screening", "competency", "deep_dive"]

# Hard wall-clock cap on the whole interview, independent of question counts.
MAX_INTERVIEW_SECONDS = 10 * 60

# Matched against the candidate's raw answer text (typed or voice-transcribed)
# before it ever reaches the LLM. Deliberately simple substring matching, not
# fuzzy NLP — these are meant to be unambiguous "I'm done" phrases, not things
# a real interview answer would ever contain incidentally.
_STOP_PHRASES = [
    "stop the interview",
    "stop this interview",
    "end the interview",
    "end this interview",
    "i want to stop",
    "i want to end the interview",
    "please stop the interview",
    "cancel the interview",
]


def _is_stop_command(answer_text: str) -> bool:
    normalized = re.sub(r"\s+", " ", answer_text.strip().lower())
    return any(phrase in normalized for phrase in _STOP_PHRASES)


def _level_question_count(session: Session, level: str) -> int:
    return sum(1 for qa in session.transcript if qa.level == level)


def _next_level(current: str) -> str:
    idx = LEVEL_ORDER.index(current)
    if idx + 1 < len(LEVEL_ORDER):
        return LEVEL_ORDER[idx + 1]
    return "done"


def _format_transcript(session: Session) -> str:
    lines = []
    for qa in session.transcript:
        if qa.answer is not None:
            lines.append(f"[{qa.level}] Q: {qa.question}\nA: {qa.answer}")
        else:
            lines.append(f"[{qa.level}] Q: {qa.question}\nA: (unanswered)")
    return "\n\n".join(lines) if lines else "(no exchanges yet)"


def _done_result(session: Session, ended_reason: str, last_evaluation: Optional[dict] = None) -> dict:
    session.current_level = "done"
    session.ended_reason = ended_reason
    return {
        "done": True,
        "level": "done",
        "next_question": None,
        "ended_reason": ended_reason,
        "last_evaluation": last_evaluation,
    }


async def start_interview(session: Session) -> Session:
    if session.role_analysis is None or session.candidate_analysis is None:
        raise ValueError("Run analysis before starting the interview.")
    if session.transcript:
        raise ValueError("Interview already started for this session.")

    data = await llm_json(
        OPENING_QUESTION_SYSTEM,
        OPENING_QUESTION_USER_TEMPLATE.format(
            role_analysis_json=session.role_analysis.model_dump_json(),
            candidate_analysis_json=session.candidate_analysis.model_dump_json(),
            resume_text=session.resume_text,
        ),
    )
    question = data["next_question"]

    session.current_level = "screening"
    session.interview_started_at = time.time()
    session.ended_reason = None
    session.transcript.append(QAExchange(level="screening", question=question))
    return session


def stop_interview(session: Session) -> dict:
    """Used by the explicit 'Stop Interview' button — ends the interview
    immediately without touching any pending question or calling the LLM."""
    if not session.transcript:
        raise ValueError("Interview has not started.")
    if session.current_level == "done":
        # Already finished (naturally, or a previous stop/time-limit) —
        # treat as a no-op success rather than an error, so a double-click
        # on the button doesn't surface a scary error message.
        return {
            "done": True,
            "level": "done",
            "next_question": None,
            "ended_reason": session.ended_reason or "user_stopped",
            "last_evaluation": None,
        }
    return _done_result(session, "user_stopped")


async def submit_answer(session: Session, answer_text: str) -> dict:
    """
    Records the answer to the last unanswered question, evaluates it, and
    either returns the next question or marks the interview done.
    Returns a dict describing what happened (for the API response).
    """
    if not session.transcript:
        raise ValueError("Interview has not started.")

    pending = next((qa for qa in reversed(session.transcript) if qa.answer is None), None)
    if pending is None:
        raise ValueError("No pending question to answer — interview may already be complete.")

    # Both checks below end the interview without ever calling the LLM —
    # there's nothing to evaluate once we know we're stopping.
    if _is_stop_command(answer_text):
        pending.answer = answer_text
        return _done_result(session, "user_stopped")

    if session.interview_started_at is not None and (time.time() - session.interview_started_at) >= MAX_INTERVIEW_SECONDS:
        pending.answer = answer_text
        return _done_result(session, "time_limit")

    pending.answer = answer_text
    current_level = session.current_level
    level_count = _level_question_count(session, current_level)

    try:
        data = await llm_json(
            NEXT_TURN_SYSTEM.format(level_instructions=LEVEL_INSTRUCTIONS[current_level]),
            NEXT_TURN_USER_TEMPLATE.format(
                role_analysis_json=session.role_analysis.model_dump_json(),
                candidate_analysis_json=session.candidate_analysis.model_dump_json(),
                current_level=current_level,
                level_question_count=level_count,
                transcript_text=_format_transcript(session),
                last_answer=answer_text,
            ),
        )
    except Exception:
        # session is the same in-memory object held by the store, so this
        # mutation is already "live" even though save_session() hasn't run
        # yet. If the LLM call fails, undo it — otherwise a retried
        # submit_answer() on the same session finds pending.answer already
        # set and raises "no pending question" instead of actually retrying.
        pending.answer = None
        raise

    pending.answer_quality = int(data.get("answer_quality", 3))
    pending.tags = list(data.get("tags", []))
    evaluation = {"answer_quality": pending.answer_quality, "tags": pending.tags}

    # Guardrails override the model's own judgement at the edges.
    force_advance = level_count >= MAX_QUESTIONS_PER_LEVEL[current_level]
    can_advance = level_count >= MIN_QUESTIONS_PER_LEVEL[current_level]
    should_advance = force_advance or (can_advance and bool(data.get("advance_level")))

    interview_complete = bool(data.get("interview_complete")) and current_level == "deep_dive"
    if force_advance and current_level == "deep_dive":
        interview_complete = True

    if interview_complete:
        return _done_result(session, "completed", evaluation)

    if should_advance:
        session.current_level = _next_level(current_level)
        if session.current_level == "done":
            return _done_result(session, "completed", evaluation)

    next_question = data.get("next_question") or ""
    if not next_question:
        # Model said not complete but gave no question — fail safe rather than
        # silently dead-ending the interview.
        next_question = "Can you walk me through another project from your resume that's relevant to this role?"

    session.transcript.append(QAExchange(level=session.current_level, question=next_question))

    return {
        "done": False,
        "level": session.current_level,
        "next_question": next_question,
        "last_evaluation": evaluation,
    }
