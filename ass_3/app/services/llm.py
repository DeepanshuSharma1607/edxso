"""
Single choke point for every LLM call (Google Gemini via the google-genai SDK).

Gemini-specific hardening:
  - response.text can be None (safety block / empty candidate / MAX_TOKENS)
  - JSON mode can still return fenced JSON, a 1-item list, or null fields
  - transient 429/5xx are retried with backoff; a retired/unknown model (404)
    or exhausted retries fall through to the fallback model once
"""
import asyncio
import json
import logging
import re

from google import genai
from google.genai import types
from google.genai.errors import APIError

from app.config import settings

logger = logging.getLogger(__name__)

_client: genai.Client | None = None

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3
_BASE_DELAY_SECONDS = 3.0
_MAX_OUTPUT_TOKENS = 8192


class LLMServiceError(RuntimeError):
    """Raised when the LLM call fails after retries or non-transiently."""


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.gemini_api_key:
            raise LLMServiceError("GEMINI_API_KEY is not set. Add it to your .env file.")
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _extract_text(response) -> str:
    """Return response text or raise a clear error if Gemini produced none."""
    try:
        text = response.text
    except Exception:  # .text can raise on multi-part / blocked responses
        text = None
    if text and text.strip():
        return text

    reason = "unknown"
    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        reason = f"prompt blocked: {feedback.block_reason}"
    elif getattr(response, "candidates", None):
        reason = f"finish_reason={response.candidates[0].finish_reason}"
    raise LLMServiceError(f"Gemini returned no text ({reason}).")


async def _call_model(model: str, system_prompt: str, user_prompt: str,
                      temperature: float, response_mime_type: str) -> str:
    client = _get_client()
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        response_mime_type=response_mime_type,
        max_output_tokens=_MAX_OUTPUT_TOKENS,
    )

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            # SDK call is synchronous — keep it off the event loop.
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=user_prompt,
                config=config,
            )
            return _extract_text(response)
        except APIError as e:
            code = getattr(e, "code", None)
            if code not in _RETRYABLE_STATUS_CODES or attempt == _MAX_ATTEMPTS:
                raise
            delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning("Gemini %s on %s, retry %d in %.0fs", code, model, attempt, delay)
            await asyncio.sleep(delay)
    raise LLMServiceError("Gemini call failed.")  # unreachable


async def _complete_with_retry(*, system_prompt: str, user_prompt: str,
                               temperature: float, response_mime_type: str = "text/plain") -> str:
    models = [settings.gemini_model]
    fallback = settings.gemini_fallback_model
    if fallback and fallback != settings.gemini_model:
        models.append(fallback)

    last_error: Exception | None = None
    for i, model in enumerate(models):
        try:
            return await _call_model(model, system_prompt, user_prompt,
                                     temperature, response_mime_type)
        except LLMServiceError as e:
            last_error = e
        except APIError as e:
            last_error = e
            code = getattr(e, "code", None)
            # 400/401/403 = bad request / bad key: a different model won't help.
            if code in (400, 401, 403):
                raise LLMServiceError(f"Gemini API rejected request ({code}): {e}") from e
        except Exception as e:
            raise LLMServiceError(f"Gemini call failed: {e}") from e
        if i + 1 < len(models):
            logger.warning("Model %s failed (%s); trying fallback %s", model, last_error, models[i + 1])

    raise LLMServiceError(f"Gemini call failed on all models: {last_error}") from last_error


async def llm_text(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    return await _complete_with_retry(
        system_prompt=system_prompt, user_prompt=user_prompt,
        temperature=temperature, response_mime_type="text/plain",
    )


async def llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
    content = await _complete_with_retry(
        system_prompt=system_prompt, user_prompt=user_prompt,
        temperature=temperature, response_mime_type="application/json",
    )
    return drop_nulls(_safe_json_parse(content))


def _safe_json_parse(content: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMServiceError(f"LLM did not return valid JSON: {e}\nRaw: {content[:500]}") from e
    # Gemini occasionally wraps the object in a single-element list.
    if isinstance(parsed, list) and len(parsed) == 1 and isinstance(parsed[0], dict):
        parsed = parsed[0]
    if not isinstance(parsed, dict):
        raise LLMServiceError(f"LLM returned JSON {type(parsed).__name__}, expected an object.")
    return parsed


def drop_nulls(data: dict) -> dict:
    """Remove null values so pydantic defaults apply (Gemini emits null for empty fields)."""
    return {k: v for k, v in data.items() if v is not None}


def as_bool(value, default: bool = False) -> bool:
    """bool("false") is True in Python — parse model output safely."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    if isinstance(value, (int, float)):
        return bool(value)
    return default


def as_int(value, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        n = int(float(str(value).strip().split("/")[0]))
    except (ValueError, TypeError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n
