# Prompt Engineering — AI Personalization Layer

Documents the LLM usage in Stage 4 (`src/personalization/personalize.py`):
the model, the prompt, why it is shaped that way, what failed before, and how
the output is verified rather than trusted.

---

## 1. Model & configuration

| Setting | Value | Why |
|---|---|---|
| Models | Gemini Flash pool, then Mistral `mistral-small-latest` | Fast and cheap enough for 69 creators × up to 4 attempts; the task is short-form copywriting, not reasoning-heavy. Multiple models because of the quota wall below |
| Structured output | Gemini `responseMimeType: application/json`; Mistral `response_format: {type: json_object}` | Forces structured output. Without it the model wraps JSON in prose/``` fences and parsing becomes brittle — `_strip_fences` is still kept as a belt-and-braces guard |
| `temperature` | `0.75` first attempt, `0.5` on retries | High enough that 69 pitches don't read identically; lowered on retry because retries are about obeying a length constraint, not being creative |
| Concurrency | 4 worker threads | Balances wall-clock against free-tier rate limits (429s are caught and backed off) |
| Retries | 2–3 per HTTP call, 4 attempts per creator | Two separate loops: transport errors vs. content-quality failures |

### The quota wall, and why one model isn't enough

Gemini's free tier allows **20 `generateContent` requests per day, per model**.
69 creators need ~90 requests including word-count retries, so a single-model
run stops dead at 20 with HTTP 429 `RESOURCE_EXHAUSTED`. This is a quota limit,
not a prompt or code problem — swapping model names confirmed the cap is
per-model, not per-key.

`call_llm` therefore tries models in order and returns which one answered:

1. **Gemini pool** (five Flash variants). Each has its own daily bucket. The
   critical detail is that **not every 429 means the same thing** — a body naming
   a *per-day* quota retires the model for the whole run, while a per-minute
   burst limit only warrants a backoff. Treating them alike would either throw
   away a healthy model or spin forever on a dead one.
2. **Mistral fallback**, metered per-minute rather than per-day, which removes
   the daily ceiling entirely.

Whichever model produced a message is written to a `generated_by` column, so the
deliverable never implies all 69 came from one model. In the committed run,
model rotation alone sufficed and Mistral was never called.

---

## 2. The prompt

Assembled in `BASE_PROMPT` and formatted per creator. Structure and the
reasoning behind each block:

```
You are an experienced Influencer Marketing Director at EDXSO,
writing genuine first-contact outreach to a YouTube creator.
```
**Role assignment.** "Marketing Director" produces a peer-to-peer business tone.
Without a role the model defaults to a stiff, formal register that reads like a
mail-merge. "genuine first-contact" discourages the false familiarity LLMs
reach for ("I've been following you for years!") which would be a lie.

```
CREATOR PROFILE (all figures are verified from the YouTube Data API):
- Name / Niche / Subscribers / Verified engagement rate
- Average views per recent upload
- Content themes
- Recent video titles
- Country
```
**Grounding data — the core of the personalization.** Every field is real
output from Stages 1–3, not invented. The parenthetical "verified from the
YouTube Data API" matters: it tells the model these numbers are safe to cite,
so it references concrete figures instead of hedging with vague praise.
`recent_video_titles` is the highest-value field — it's what makes the opening
line provably specific to that one creator.

```
PROPOSED COLLABORATION ANGLE: {angle}
Build the pitch around this specific angle. Do not substitute a different one.
```
**Constraint injection.** See §3 — this exists because the model would not
otherwise vary the angle.

```
1. "email_pitch"
   - MUST be between 60 and 90 words. This is a hard limit.
   - Open by referencing something concrete and specific from their actual
     content themes or recent video titles. Never generic flattery.
   - Name the collaboration angle and one clear value proposition for them.
   - End with a specific, low-friction call to action.
   - Warm and professional. No emoji. No placeholder text like [Brand].
   - Do not include a greeting line, signature, or subject inside this field.
```
Each bullet is a defect guard learned from output inspection:

| Instruction | Failure it prevents |
|---|---|
| "Never generic flattery" | "Your content is amazing!" — indistinguishable across creators |
| "No placeholder text like `[Brand]`" | The model emitting unfilled template slots into a message meant to be sent |
| "Do not include a greeting/signature" | Double greetings — `send.py` adds `Hi {name},` and the signature deterministically, so the LLM writing its own produced "Hi X, Hi X," |
| "low-friction call to action" | Vague closers ("let me know your thoughts") that give the recipient nothing to act on |
| "No emoji" | Emoji in a first-contact business email, plus they inflate word counts unpredictably |

```
3. "instagram_dm"
   - MUST be between 15 and 30 words.
   - Casual and human, like a real person who watched their videos.
   - Reference their content specifically, then invite a conversation.
```
Deliberately a *different voice* from the email — DMs read as spam when written
in email register. "like a real person who watched their videos" is the tone
lever; the SPEC's own example (`"loved your recent skincare routine content"`)
is that register.

```
Return ONLY a valid JSON object with exactly these keys:
{"collaboration_angle": "...", "email_subject": "...",
 "email_pitch": "...", "instagram_dm": "..."}
```
Explicit schema echo. Combined with `responseMimeType: application/json` this
made parse failures effectively vanish.

---

## 3. Problem: the model collapsed to one collaboration angle

The SPEC lists six angles (sponsorship, affiliate, UGC, brand ambassador, paid
product placement, barter). Asked to "choose an appropriate angle," the model
chose **Sponsored Integration for all 78 creators** — technically valid, but it
defeats the requirement and makes the batch look templated.

**Fix — decide the angle in code, not in the prompt.** `pick_collaboration_angle()`
assigns one before the API call and the prompt receives it as a fixed
constraint. Assignment is:

- **Niche-aware** — `NICHE_ANGLE_PREFERENCE` maps each niche to angles that
  actually make commercial sense (Beauty → UGC/barter; Technology → paid
  product placement; Finance → sponsored/affiliate).
- **Size-aware** — creators under 15k subscribers skew toward barter / UGC /
  affiliate (realistic for that tier); larger ones toward paid integrations and
  ambassadorships.
- **Deterministic, not random** — the index is `sum(ord(c) for c in channel_id) % len(prefs)`.
  A random pick would give a different angle on every re-run, so cached and
  freshly-generated messages would disagree and the pipeline would stop being
  reproducible.

---

## 4. Problem: word counts were ignored

The SPEC sets hard bounds (email 60–90, DM 15–30). Stating them in the prompt
was not enough — an earlier full run put **77 of 78 email pitches outside the
range**, spanning 41–99 words. LLMs do not count words reliably.

**Fix — verify in code and retry with corrective feedback.** The bounds are
treated as a testable postcondition:

1. Generate.
2. Count words (`word_count`) and measure how far out of bounds it is (`_range_miss`).
3. If non-compliant, append explicit feedback naming the actual number and
   re-request, up to `MAX_ATTEMPTS = 4`:

```
YOUR PREVIOUS ATTEMPT WAS REJECTED:
Your email_pitch was 96 words, which breaks the 60-90 word limit — cut it down.
Count your words before answering. Keep the same specific references to their
content; only fix the length.
```

Naming the measured count ("was 96 words") works far better than repeating the
rule, and "keep the same specific references; only fix the length" stops the
model from throwing away good personalization while fixing arithmetic.

4. The closest-to-compliant attempt is retained as `best`, so a stubborn
   profile still yields the best available message.
5. Every record carries `word_count_compliant` and `generation_attempts`, so
   compliance is an auditable column in the output CSV rather than a claim.

The cache honours this too — `if cached.get("word_count_compliant")` — so a
non-compliant cached message is never reused.

---

## 5. Honest failure

If all 4 attempts fail (e.g. API outage), the creator's message fields are left
**empty** and `word_count_compliant` is `False`. An earlier version fell back to
a fixed template string, which would have shipped a fabricated "personalized"
message — contrary to SPEC §10. `send.py` then records that creator as
`SKIPPED_NO_MESSAGE` rather than pretending to send.

---

## 6. Other prompt-free AI-ish logic

`derive_content_themes()` in Stage 3 does **not** use an LLM. Themes are derived
by keyword frequency over real recent video titles plus the channel
description. This is deliberate: it's cheap, deterministic, and cannot
hallucinate a theme the creator doesn't actually cover — and its output then
becomes grounding input for the Stage 4 prompt.
