"""
personalize.py — Stage 4: AI-Powered Message Personalization
============================================================
Generates two dynamic outreach messages per shortlisted creator using the
Google Gemini API:

  A. Email collaboration pitch  — strictly 60-90 words + a subject line
  B. Instagram DM               — strictly 15-30 words

Word-count compliance
---------------------
The SPEC states hard word bounds, and an LLM asked politely for "60-90 words"
misses them often — an earlier run of this project put 77 of 78 pitches outside
the range (41-99 words). So the bounds are *verified in code*, not trusted:
each candidate is counted, and out-of-range output is regenerated with explicit
corrective feedback ("you wrote 96 words, cut it to 60-90") for up to
MAX_ATTEMPTS tries. The closest-to-range attempt is kept as a fallback so a
stubborn creator profile still yields the best available message rather than a
canned template.

Collaboration-angle variety
---------------------------
The SPEC lists six angles and asks for tailoring. Left to itself the model
picked "Sponsored Integration" for all 78 creators. Each creator is now
assigned a candidate angle deterministically from their channel_id (stable
across re-runs, no randomness that would break resume/caching) weighted by what
suits their niche and audience size, and the model is instructed to build the
pitch around that angle.

Personalisation inputs are real: recent video titles, derived content themes,
verified engagement rate and subscriber count all come from Stages 1-3.
"""

import argparse
import csv
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import requests
import threading
from ass_1.src.utils.config import (
    GEMINI_API_KEY,
    MISTRAL_API_KEY,
    ENRICHED_PROFILES_JSON,
    PERSONALIZED_CSV,
    PERSONALIZED_JSON,
    CACHE_FILE,
)

# Two providers, tried in order. Gemini's free tier caps generateContent at 20
# requests per DAY per MODEL, so a 69-creator run (~100 requests with word-count
# retries) cannot complete on Gemini alone — rotating models buys ~100/day and
# is still fragile. Mistral's free tier is metered per-minute rather than
# per-day, so it acts as the backstop once every Gemini model is spent.
# Whichever model actually produced a message is recorded in `generated_by`,
# so the deliverable never implies all 69 came from one model (SPEC section 10).
MODEL_POOL = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL",
    "gemini-3.5-flash,gemini-3.6-flash,gemini-flash-lite-latest,"
    "gemini-3.1-flash-lite,gemini-3.5-flash-lite",
).split(",") if m.strip()]

MISTRAL_POOL = [m.strip() for m in os.environ.get(
    "MISTRAL_MODEL", "mistral-small-latest",
).split(",") if m.strip()]

MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"

# Models retired for the rest of this run (daily cap hit, or not available to
# this key). Shared across worker threads, hence the lock.
_EXHAUSTED: set[str] = set()
_EXHAUSTED_LOCK = threading.Lock()


def _retire(model: str, why: str) -> None:
    with _EXHAUSTED_LOCK:
        if model not in _EXHAUSTED:
            _EXHAUSTED.add(model)
            log.warning("Retiring model %s for this run (%s).", model, why)


def _is_retired(model: str) -> bool:
    with _EXHAUSTED_LOCK:
        return model in _EXHAUSTED


def _api_url(model: str) -> str:
    return (f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={GEMINI_API_KEY}")

EMAIL_MIN_WORDS, EMAIL_MAX_WORDS = 60, 90
DM_MIN_WORDS, DM_MAX_WORDS = 15, 30
MAX_ATTEMPTS = 4
MAX_WORKERS = 4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# Angle -> which niches and audience sizes it suits best.
COLLABORATION_ANGLES = [
    "Sponsored Integration",
    "UGC Content Creation",
    "Affiliate Partnership",
    "Brand Ambassador Program",
    "Paid Product Placement",
    "Barter Collaboration",
]

NICHE_ANGLE_PREFERENCE = {
    "Technology": ["Paid Product Placement", "Sponsored Integration", "Affiliate Partnership"],
    "Beauty":     ["UGC Content Creation", "Barter Collaboration", "Brand Ambassador Program"],
    "Fitness":    ["Brand Ambassador Program", "Affiliate Partnership", "UGC Content Creation"],
    "Finance":    ["Sponsored Integration", "Affiliate Partnership", "Brand Ambassador Program"],
    "Gaming":     ["Sponsored Integration", "UGC Content Creation", "Paid Product Placement"],
}


def pick_collaboration_angle(creator: dict) -> str:
    """Deterministically assign a niche-appropriate angle.

    Deterministic (hashed off channel_id, not random) so re-runs and the
    on-disk cache stay consistent. Smaller creators skew toward barter/UGC
    offers, larger ones toward paid integrations and ambassadorships.
    """
    niche = creator.get("niche", "")
    subs = int(float(creator.get("subscriber_count", 0) or 0))
    prefs = list(NICHE_ANGLE_PREFERENCE.get(niche, COLLABORATION_ANGLES))

    if subs < 15_000:
        for low_budget in ("Barter Collaboration", "UGC Content Creation", "Affiliate Partnership"):
            if low_budget not in prefs:
                prefs.append(low_budget)
    else:
        for paid in ("Sponsored Integration", "Brand Ambassador Program"):
            if paid not in prefs:
                prefs.append(paid)

    cid = str(creator.get("channel_id", "")) or creator.get("influencer_name", "x")
    idx = sum(ord(c) for c in cid) % len(prefs)
    return prefs[idx]


BASE_PROMPT = """You are an experienced Influencer Marketing Director at EDXSO, \
writing genuine first-contact outreach to a YouTube creator.

CREATOR PROFILE (all figures are verified from the YouTube Data API):
- Name: {name}
- Niche: {niche}
- Subscribers: {subscribers:,}
- Verified engagement rate: {engagement_rate}% (likes + comments / views on recent uploads)
- Average views per recent upload: {avg_views:,}
- Content themes: {content_themes}
- Recent video titles: {recent_videos}
- Country: {country}

PROPOSED COLLABORATION ANGLE: {angle}
Build the pitch around this specific angle. Do not substitute a different one.

WRITE TWO MESSAGES:

1. "email_pitch" — a collaboration email body.
   - MUST be between {email_min} and {email_max} words. This is a hard limit.
   - Open by referencing something concrete and specific from their actual \
content themes or recent video titles. Never generic flattery.
   - Name the collaboration angle and one clear value proposition for them.
   - End with a specific, low-friction call to action.
   - Warm and professional. No emoji. No placeholder text like [Brand].
   - Do not include a greeting line, signature, or subject inside this field.

2. "email_subject" — one specific, non-clickbait subject line under 12 words \
that references their niche or content.

3. "instagram_dm" — a short direct message.
   - MUST be between {dm_min} and {dm_max} words. This is a hard limit.
   - Casual and human, like a real person who watched their videos.
   - Reference their content specifically, then invite a conversation.

Return ONLY a valid JSON object with exactly these keys:
{{"collaboration_angle": "{angle}", "email_subject": "...", \
"email_pitch": "...", "instagram_dm": "..."}}"""


def word_count(text: str) -> int:
    return len((text or "").split())


def _in_range(n: int, lo: int, hi: int) -> bool:
    return lo <= n <= hi


def _range_miss(email_words: int, dm_words: int) -> int:
    """How far outside the allowed bounds this candidate is, in total words."""
    miss = 0
    if email_words < EMAIL_MIN_WORDS:
        miss += EMAIL_MIN_WORDS - email_words
    elif email_words > EMAIL_MAX_WORDS:
        miss += email_words - EMAIL_MAX_WORDS
    if dm_words < DM_MIN_WORDS:
        miss += DM_MIN_WORDS - dm_words
    elif dm_words > DM_MAX_WORDS:
        miss += dm_words - DM_MAX_WORDS
    return miss


def _strip_fences(raw: str) -> str:
    """Some models wrap JSON in a markdown fence despite being asked not to."""
    raw = raw.strip()
    for fence in ("```json", "```"):
        if raw.startswith(fence):
            raw = raw[len(fence):]
    if raw.endswith("```"):
        raw = raw[:-3]
    return raw.strip()


def _call_gemini_model(model: str, prompt: str, temperature: float) -> dict | None:
    """One Gemini model, with short retries. Retires the model on a daily cap."""
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    for attempt in range(2):
        try:
            resp = requests.post(_api_url(model), json=payload, timeout=45)
            if resp.status_code == 429:
                # A per-day cap is permanent for this run; a per-minute burst
                # limit just needs a pause. Only the former retires the model.
                if "PerDay" in resp.text or "per day" in resp.text:
                    _retire(model, "daily free-tier cap reached")
                    return None
                time.sleep((attempt + 1) * 4)
                continue
            if resp.status_code in (400, 403, 404):
                _retire(model, f"HTTP {resp.status_code} — not usable with this key")
                return None
            if resp.status_code >= 500:
                time.sleep((attempt + 1) * 2)
                continue
            resp.raise_for_status()
            raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(_strip_fences(raw))
        except Exception as e:
            log.debug("Gemini %s failed (attempt %d): %s", model, attempt + 1, e)
            time.sleep(1.5)
    return None


def _call_mistral_model(model: str, prompt: str, temperature: float) -> dict | None:
    """One Mistral model. OpenAI-shaped chat completions with JSON mode."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    for attempt in range(3):
        try:
            resp = requests.post(MISTRAL_URL, json=payload, headers=headers, timeout=60)
            if resp.status_code == 429:
                # Mistral's free tier limits requests per second, not per day,
                # so a 429 here is a burst — back off and retry, never retire.
                time.sleep((attempt + 1) * 3)
                continue
            if resp.status_code in (401, 403):
                _retire(model, f"HTTP {resp.status_code} — key rejected")
                return None
            if resp.status_code >= 500:
                time.sleep((attempt + 1) * 2)
                continue
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            return json.loads(_strip_fences(raw))
        except Exception as e:
            log.debug("Mistral %s failed (attempt %d): %s", model, attempt + 1, e)
            time.sleep(1.5)
    return None


def call_llm(prompt: str, temperature: float = 0.75) -> tuple[dict | None, str]:
    """Try every live model across both providers; return (parsed, model_used).

    Gemini first (it is the provider the assignment names), Mistral as the
    backstop once Gemini's per-day caps are spent. `model_used` is threaded
    into the output so each row states which model wrote it.
    """
    for model in MODEL_POOL:
        if _is_retired(model):
            continue
        parsed = _call_gemini_model(model, prompt, temperature)
        if parsed is not None:
            return parsed, model

    if MISTRAL_API_KEY:
        for model in MISTRAL_POOL:
            if _is_retired(model):
                continue
            parsed = _call_mistral_model(model, prompt, temperature)
            if parsed is not None:
                return parsed, model

    return None, ""


def generate_messages_for_creator(creator: dict) -> dict:
    """Generate messages, verifying the SPEC word bounds and retrying with
    corrective feedback until they hold (or MAX_ATTEMPTS is reached)."""
    angle = pick_collaboration_angle(creator)
    recent = (creator.get("recent_video_titles", "") or "").replace(" || ", "; ")

    prompt = BASE_PROMPT.format(
        name=creator.get("influencer_name", "Creator"),
        niche=creator.get("niche", "General"),
        subscribers=int(float(creator.get("subscriber_count", 0) or 0)),
        engagement_rate=creator.get("engagement_rate_pct", 0),
        avg_views=int(float(creator.get("avg_recent_views", 0) or 0)),
        content_themes=creator.get("content_themes", "N/A"),
        recent_videos=recent[:400] or "N/A",
        country=creator.get("country") or "India",
        angle=angle,
        email_min=EMAIL_MIN_WORDS, email_max=EMAIL_MAX_WORDS,
        dm_min=DM_MIN_WORDS, dm_max=DM_MAX_WORDS,
    )

    best: dict | None = None
    best_miss = 10**6
    feedback = ""

    for attempt in range(1, MAX_ATTEMPTS + 1):
        parsed, model_used = call_llm(
            prompt + feedback, temperature=0.75 if attempt == 1 else 0.5
        )
        if not parsed:
            continue

        pitch = (parsed.get("email_pitch") or "").strip()
        dm = (parsed.get("instagram_dm") or "").strip()
        ew, dw = word_count(pitch), word_count(dm)
        miss = _range_miss(ew, dw)

        if miss < best_miss:
            best_miss = miss
            best = {
                "collaboration_angle": angle,
                "email_subject": (parsed.get("email_subject") or "").strip()
                    or f"Collaboration idea for {creator.get('influencer_name')}",
                "email_pitch": pitch,
                "email_word_count": ew,
                "instagram_dm": dm,
                "dm_word_count": dw,
                "generation_attempts": attempt,
                "word_count_compliant": miss == 0,
                "generated_by": model_used,
            }

        if miss == 0:
            best["generation_attempts"] = attempt
            return best

        # Corrective feedback — tell the model exactly what it got wrong.
        problems = []
        if not _in_range(ew, EMAIL_MIN_WORDS, EMAIL_MAX_WORDS):
            direction = "expand it" if ew < EMAIL_MIN_WORDS else "cut it down"
            problems.append(
                f"Your email_pitch was {ew} words, which breaks the "
                f"{EMAIL_MIN_WORDS}-{EMAIL_MAX_WORDS} word limit — {direction}."
            )
        if not _in_range(dw, DM_MIN_WORDS, DM_MAX_WORDS):
            direction = "expand it" if dw < DM_MIN_WORDS else "cut it down"
            problems.append(
                f"Your instagram_dm was {dw} words, which breaks the "
                f"{DM_MIN_WORDS}-{DM_MAX_WORDS} word limit — {direction}."
            )
        feedback = (
            "\n\nYOUR PREVIOUS ATTEMPT WAS REJECTED:\n"
            + "\n".join(problems)
            + "\nCount your words before answering. Keep the same specific "
              "references to their content; only fix the length."
        )
        time.sleep(0.4)

    if best:
        return best

    # Total API failure for this creator — record it honestly rather than
    # shipping a fabricated "personalized" message.
    return {
        "collaboration_angle": angle,
        "email_subject": "",
        "email_pitch": "",
        "email_word_count": 0,
        "instagram_dm": "",
        "dm_word_count": 0,
        "generation_attempts": MAX_ATTEMPTS,
        "word_count_compliant": False,
        "generated_by": "",
    }


OUTPUT_FIELDS = [
    "channel_id", "influencer_name", "platform", "niche",
    "subscriber_count", "engagement_rate_pct", "avg_recent_views",
    "contact_email", "instagram_url",
    "collaboration_angle", "email_subject", "email_pitch", "email_word_count",
    "instagram_dm", "dm_word_count", "word_count_compliant",
    "generation_attempts", "generated_by", "content_themes",
    "recent_video_titles", "profile_url", "personalized_at",
]


def save_csv(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)
    log.info("CSV saved -> %s (%d rows)", path, len(records))


def save_json(records: list[dict], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    log.info("JSON saved -> %s (%d records)", path, len(records))


def run_personalize(force: bool = False) -> list[dict]:
    log.info("=== Stage 4: AI Message Personalization ===")

    if not GEMINI_API_KEY:
        log.error("GEMINI_API_KEY missing from .env — cannot generate messages.")
        return []
    if not os.path.exists(ENRICHED_PROFILES_JSON):
        log.error("Enriched profiles not found at %s!", ENRICHED_PROFILES_JSON)
        return []

    with open(ENRICHED_PROFILES_JSON, encoding="utf-8") as f:
        creators = json.load(f)

    cache: dict = {}
    if os.path.exists(CACHE_FILE) and not force:
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}
    log.info(
        "Personalizing %d creators (%d already cached)%s",
        len(creators), len(cache), " — forced regeneration" if force else "",
    )

    def process(creator: dict) -> dict:
        cid = creator.get("channel_id", "")
        cached = cache.get(cid)
        # Only reuse a cached message if it actually met the word bounds.
        if cached and cached.get("word_count_compliant") and not force:
            # Entries cached before `generated_by` existed did not record their
            # model. Say so rather than guessing a name into the deliverable.
            cached.setdefault("generated_by", "gemini (cached, model not recorded)")
            return cached

        msg = generate_messages_for_creator(creator)
        record = {
            "channel_id": cid,
            "influencer_name": creator.get("influencer_name", "Unknown"),
            "platform": creator.get("platform", "YouTube"),
            "niche": creator.get("niche"),
            "subscriber_count": creator.get("subscriber_count"),
            "engagement_rate_pct": creator.get("engagement_rate_pct"),
            "avg_recent_views": creator.get("avg_recent_views"),
            "contact_email": creator.get("contact_email"),
            "instagram_url": creator.get("instagram_url"),
            "content_themes": creator.get("content_themes"),
            "recent_video_titles": creator.get("recent_video_titles"),
            "profile_url": creator.get("profile_url"),
            "personalized_at": datetime.now(timezone.utc).isoformat(),
            **msg,
        }
        cache[cid] = record
        return record

    results_map: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        for rec in pool.map(process, creators):
            results_map[rec["channel_id"]] = rec

    results = [results_map[c["channel_id"]] for c in creators if c["channel_id"] in results_map]

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception as e:
        log.warning("Could not write personalization cache: %s", e)

    save_csv(results, PERSONALIZED_CSV)
    save_json(results, PERSONALIZED_JSON)

    compliant = sum(1 for r in results if r.get("word_count_compliant"))
    empty = sum(1 for r in results if not r.get("email_pitch"))
    angles = {}
    for r in results:
        angles[r.get("collaboration_angle", "?")] = angles.get(r.get("collaboration_angle", "?"), 0) + 1
    avg_attempts = (
        sum(int(r.get("generation_attempts", 1) or 1) for r in results) / len(results)
        if results else 0
    )

    print("\n" + "=" * 70)
    print("AI Personalization Complete")
    print(f"  Messages generated       : {len(results)}")
    print(f"  Word-count compliant     : {compliant}/{len(results)}")
    print(f"  Failed / empty           : {empty}")
    print(f"  Avg generation attempts  : {avg_attempts:.2f}")
    print(f"  Unique subject lines     : {len({r.get('email_subject') for r in results})}")
    print("  Collaboration angle mix  :")
    for angle, n in sorted(angles.items(), key=lambda kv: -kv[1]):
        print(f"      {angle:<28} {n}")
    by_model: dict[str, int] = {}
    for r in results:
        by_model[r.get("generated_by") or "(failed)"] = \
            by_model.get(r.get("generated_by") or "(failed)", 0) + 1
    print("  Generated by model       :")
    for m, n in sorted(by_model.items(), key=lambda kv: -kv[1]):
        print(f"      {m:<40} {n}")
    if _EXHAUSTED:
        print(f"  Models retired this run  : {', '.join(sorted(_EXHAUSTED))}")
    print(f"  CSV  -> {PERSONALIZED_CSV}")
    print(f"  JSON -> {PERSONALIZED_JSON}")
    print("=" * 70 + "\n")

    return results


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Stage 4: AI Message Personalization")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Ignore the cache and regenerate every message from scratch",
    )
    args = ap.parse_args()
    run_personalize(force=args.force)
