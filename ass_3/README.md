# Interview Accelerator — Build Progress

Stack: FastAPI (Python), Mistral API (LLM), faster-whisper `tiny` (STT, local/CPU),
edge-tts (TTS, free). Server-rendered templates (Jinja2 + vanilla JS) — no Node
build step, matches CPU-only dev environment.

## Status: Phase 1–8 of 9 complete, Phase 9 in progress

- [x] Phase 1 — Foundation (FastAPI skeleton, LLM wrapper, routing)
- [x] Phase 2 — JD & Resume ingestion (paste + PDF/DOCX/TXT upload, extraction, validation)
- [x] Phase 3 — Role & Candidate Analysis + Job Fit scoring (dashboard UI included)
- [x] Phase 4 — Interview question engine (adaptive prompt, level guardrails, follow-up logic)
- [x] Phase 5 — Text-based interview loop (chat UI at `/interview`)
- [x] Phase 6 — Voice layer (faster-whisper STT + edge-tts TTS) — mandatory
  - includes: "stop the interview" voice/text command, a Stop Interview button, and a hard 10-minute wall-clock cap — all three end the interview without an extra LLM call and record why in `ended_reason`
- [x] Phase 7 — Evaluation & report generation (deterministic per-level/overall scoring + LLM-written narrative, cached per session, rendered on the interview page once it ends)
- [x] Phase 8 — Report UI + polish (color-coded score/readiness badge, card-based layout, live countdown badge with warning/critical color states)
- [ ] Phase 9 — Deployment & submission packaging (`.gitignore` and a placeholder `.env.example` are in now; a live deployment URL, if your brief requires one, is still an open decision — see "Before you submit" below)

## Setup

```bash
cd interview-accelerator
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and add your MISTRAL_API_KEY
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## What works right now

1. Paste or upload a JD (PDF/DOCX/TXT)
2. Paste or upload a Resume (PDF/DOCX/TXT)
3. Click "Analyse" → Mistral extracts structured Role Analysis, Candidate
   Analysis, and computes a Job Fit score with strong/partial/missing skill
   buckets.
4. Click "Start Interview →" (or go to `/interview?session_id=...`) to run a
   full adaptive text-based interview: Screening → Competency → Deep-Dive,
   with each question generated from the previous answer, the resume, and the
   JD — not a fixed question bank.
5. On the interview page: click **🎤 Record Answer** to speak instead of
   typing. It records via the browser's MediaRecorder API, uploads the audio,
   transcribes it with faster-whisper (`tiny`, runs on CPU), and feeds the
   transcript into the exact same evaluation/next-question pipeline as typed
   answers. Each AI question is also spoken aloud via edge-tts (toggle with
   the "Speak questions aloud" checkbox).

Session state is in-memory only right now (resets on server restart) — that's
intentional for this stage, so we can validate the LLM pipeline before adding
DB persistence.

### How the adaptive interview state machine works (`app/services/interview.py`)

- One LLM call per turn does double duty: evaluates the just-submitted answer
  (1-5 quality score + tags like `weak_area:system_design`) AND generates the
  next question in the same response, so the follow-up genuinely reacts to
  what the candidate just said.
- Level progression (screening → competency → deep_dive → done) is decided by
  the model's `advance_level` signal, but bounded by hard-coded
  `MIN_QUESTIONS_PER_LEVEL` / `MAX_QUESTIONS_PER_LEVEL` guardrails — tested
  with a mocked LLM that always refuses to advance, and the state machine
  still force-terminates in 14 turns rather than looping forever.
- Verified with `unittest.mock` end-to-end (analysis → interview start →
  multi-turn answer loop → completion) since no live Mistral key was available
  in the build environment — logic is confirmed correct, but **the actual
  prompt quality/question relevance still needs a real run with your API key**
  before you trust it for a demo.

## Architecture notes

- `app/services/llm.py` — single choke point for all Mistral calls
  (`llm_json` / `llm_text`). Nothing else touches the Mistral SDK directly.
- `app/prompts/` — all prompt templates live here, separate from orchestration
  logic in `app/services/analysis.py`.
- `app/models/schemas.py` — the `Session` object is the single source of
  truth for JD text, resume text, analysis results, and (once Phase 4/5 land)
  the full interview transcript and adaptive state.
- `app/services/store.py` — in-memory session store, swappable for
  Postgres/Redis without touching router code.

## Next steps

Phase 7 (report generation) is done — see `app/services/report.py`. What's
actually left before this is submission-ready:

1. **Test the mic recording path live** — `/interview/voice-answer` has not
   yet been exercised with a real recording (only typed answers have been
   confirmed against the live API so far). See the voice section below.
2. **Decide the "mandatory voice" question** — the interview currently
   accepts typed answers even with voice off. If your brief requires the
   candidate to actually use voice (not just have it available), that needs
   a code change (e.g. disable text submission, or require N voice answers
   per level) — it isn't one yet.
3. **Rotate your Mistral API key** if it's ever been shared, committed, or
   pasted anywhere outside your local `.env` — `.env` is now gitignored, but
   that only prevents *future* leaks.
4. **Decide on deployment** — a live URL (Render/Railway/etc.) vs. a local
   run + repo submission, per whatever your assignment brief actually asks
   for.

## ⚠️ Voice layer — TTS confirmed live, STT still unverified (read before demoing)

Update: a live run against the real Mistral API confirmed `/api/tts` working
end-to-end (questions were audibly spoken during a real interview turn). The
**microphone → faster-whisper transcription path (`/interview/voice-answer`)
has not yet been exercised** — every real run so far has answered by typing,
not recording. Test the 🎤 Record Answer button with an actual microphone
before considering voice input "done," not just voice output.

1. Click **🎤 Record Answer**, speak an answer, confirm it transcribes
   correctly and the interview proceeds normally from the transcript.
2. First voice-answer request will be slow (faster-whisper model
   download + load on first call, ~75MB for the `tiny` model) — subsequent
   ones are fast on CPU.
3. If `transcribe_audio_bytes` throws, check that `ffmpeg`/`libav` is on your
   system PATH — PyAV (faster-whisper's audio decoder) needs it to decode the
   browser's webm/opus recordings.
