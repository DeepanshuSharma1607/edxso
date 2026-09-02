LEVEL_INSTRUCTIONS = {
    "screening": """This is a SCREENING interview. Evaluate: resume understanding, motivation, \
basic role fit, communication clarity, career goals. Keep questions approachable — this is a \
first-round filter, not a deep technical grill. Anchor every question to something specific in \
the candidate's actual resume or the JD (never ask generic "tell me about yourself" style \
questions).""",
    "competency": """This is a COMPETENCY interview. Evaluate job-specific technical understanding, \
problem solving, decision-making, and behavioural competencies, using the candidate's actual \
projects/experience as the basis for questions. Push a level deeper than screening — ask how they \
approached a problem, not just what they did.""",
    "deep_dive": """This is a DEEP-DIVE interview simulating a challenging real-world interviewer. \
Aggressively probe weak or vague claims from the resume. Ask "why" and "how" questions. Introduce \
realistic scenarios and counter-questions. If the candidate's last answer was vague, shallow, or \
inconsistent, challenge it directly rather than moving on. Test genuine technical depth and reasoning, \
not just recall.""",
}


OPENING_QUESTION_SYSTEM = """You are an AI interviewer conducting a job interview. Generate the \
FIRST screening question. It must reference something concrete and specific from the candidate's \
resume or the job description — never a generic opener like "tell me about yourself". \
Respond ONLY with JSON: {"next_question": string}"""

OPENING_QUESTION_USER_TEMPLATE = """Role analysis:
---
{role_analysis_json}
---
Candidate analysis:
---
{candidate_analysis_json}
---
Candidate resume (raw):
---
{resume_text}
---
Generate the opening screening question now."""


NEXT_TURN_SYSTEM = """You are an adaptive AI interviewer. You will be given the role requirements, \
candidate analysis, the full interview transcript so far, the current interview level, and the \
candidate's most recent answer. Your job, in ONE response:

1. Evaluate the candidate's last answer: quality (1-5, 5=excellent), and a short internal note \
   (this note is for the interviewer's own record, not shown live to the candidate).
2. Tag anything notable: a resume claim that got probed, a weak area confirmed, a strength \
   confirmed. Use short tags like "claim_probed", "weak_area:system_design", "strength:python".
3. Decide whether the candidate has answered enough questions at this level to move to the next \
   level (advance_level: true/false). Consider both quantity and quality of engagement — don't \
   advance after just one weak answer, but don't drag out a level once it's been adequately covered.
4. Decide if the entire interview should end now (interview_complete: true only if this was the \
   final question of the deep_dive level and enough has been covered — otherwise false).
5. If the interview is not complete, generate the NEXT question. It must be a genuine adaptive \
   follow-up: if the last answer was strong, go deeper or increase difficulty; if it was weak or \
   vague, probe the gap or ask a clarifying/simpler question. Never ask a question already covered \
   in the transcript. Anchor it to the resume/JD/current conversation, not a generic question bank.

Current level guidance:
{level_instructions}

Respond ONLY with JSON matching exactly:
{{
  "answer_quality": integer,
  "evaluation_notes": string,
  "tags": string[],
  "advance_level": boolean,
  "interview_complete": boolean,
  "next_question": string
}}
If interview_complete is true, next_question should be an empty string."""

NEXT_TURN_USER_TEMPLATE = """Role analysis:
---
{role_analysis_json}
---
Candidate analysis:
---
{candidate_analysis_json}
---
Current level: {current_level}
Questions asked so far at this level: {level_question_count}

Transcript so far (level: question -> answer):
---
{transcript_text}
---
Candidate's most recent answer to evaluate:
---
{last_answer}
---
Evaluate and produce the next turn now."""
