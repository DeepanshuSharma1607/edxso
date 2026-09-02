"""
Single choke point for all LLM calls. Every prompt in the app goes through
llm_json() or llm_text(). This keeps the app model-agnostic if we ever swap
providers — nothing outside this file should import the mistral SDK directly.

Mistral's API returns transient 503/429s under load (seen in practice, not
hypothetical — that's what was crashing /interview/start with an unhandled
500). Those are worth a couple of quick retries before giving up. Anything
that still fails — transient-exhausted or a genuinely different error — comes
out as LLMServiceError, a clean exception callers can catch and turn into a
proper HTTP response instead of leaking an SDK traceback to the client.
"""
import asyncio
import json
import logging
import random
import re

from mistralai.client.errors.sdkerror import SDKError
from mistralai.client.sdk import Mistral
from app.config import settings

logger = logging.getLogger(__name__)

_client: Mistral | None = None

# Status codes worth retrying — overload / rate-limit / upstream hiccups.
# Anything else (auth, bad request) retrying won't fix.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
# Mistral's own incident history shows most Chat Completions overload blips
# resolve within well under a minute, so it's worth waiting through a wider
# window here (~2+4+8s = 14s) rather than giving up after ~4s.
_MAX_ATTEMPTS = 4
_FALLBACK_MAX_ATTEMPTS = 2  # keeps primary+fallback worst case to ~14s + ~4s, not ~28s
_BASE_DELAY_SECONDS = 2.0


class LLMServiceError(RuntimeError):
    """Raised when the LLM call fails after retries (or fails non-transiently).

    Callers (routers) should catch this and return a 503 with str(e) as the
    detail, rather than letting it surface as an unhandled 500.
    """


class _RetriesExhausted(LLMServiceError):
    """Internal: the primary model failed only because of transient overload
    (429/5xx) after using up its retry budget — worth trying the fallback
    model for. A non-retryable failure (bad request, auth) raises plain
    LLMServiceError instead and skips the fallback, since a different model
    won't fix a malformed request."""


def _get_client() -> Mistral:
    global _client
    if _client is None:
        if not settings.mistral_api_key:
            raise RuntimeError(
                "MISTRAL_API_KEY is not set. Add it to your .env file."
            )
        _client = Mistral(api_key=settings.mistral_api_key)
    return _client


async def _complete_on_model(*, model: str, messages: list[dict], temperature: float, response_format: dict | None, max_attempts: int) -> str:
    """Retry loop against a single model. Raises _RetriesExhausted if it only
    ever hit retryable (overload/rate-limit) errors, or plain LLMServiceError
    for a non-retryable failure."""
    client = _get_client()
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            kwargs = dict(model=model, temperature=temperature, messages=messages)
            if response_format is not None:
                kwargs["response_format"] = response_format
            resp = await client.chat.complete_async(**kwargs)
            return resp.choices[0].message.content
        except SDKError as e:
            status_code = getattr(e.raw_response, "status_code", None)
            last_error = e
            retryable = status_code in _RETRYABLE_STATUS_CODES
            if not retryable:
                logger.warning("Mistral call (%s) failed non-retryably (status=%s): %s", model, status_code, e)
                raise LLMServiceError(f"The AI service rejected the request (status {status_code}): {e}") from e
            if attempt == max_attempts:
                logger.warning("Mistral call (%s) still failing after %d attempts (status=%s): %s", model, max_attempts, status_code, e)
                raise _RetriesExhausted(
                    f"The AI service is temporarily unavailable (status {status_code}) on model '{model}'."
                ) from e
            delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
            logger.info("Mistral call (%s) hit status=%s, retrying in %.1fs (attempt %d/%d)", model, status_code, delay, attempt, max_attempts)
            await asyncio.sleep(delay)
        except Exception as e:
            # Non-SDK failures (network drop, timeout, etc.) — don't retry
            # blindly since we don't know the cause, but never let the raw
            # exception leak past this module.
            last_error = e
            logger.exception("Unexpected error calling Mistral (%s)", model)
            raise LLMServiceError(f"The AI service call failed unexpectedly: {e}") from e

    # Unreachable, but keeps type-checkers happy.
    raise LLMServiceError(f"The AI service call failed: {last_error}")


async def _complete_with_retry(*, messages: list[dict], temperature: float, response_format: dict | None = None) -> str:
    primary = settings.mistral_model
    fallback = settings.mistral_fallback_model

    try:
        return await _complete_on_model(model=primary, messages=messages, temperature=temperature, response_format=response_format, max_attempts=_MAX_ATTEMPTS)
    except _RetriesExhausted as primary_error:
        if not fallback or fallback == primary:
            raise LLMServiceError(
                f"{primary_error} Please wait a few seconds and try again."
            ) from primary_error
        logger.info("Primary model '%s' exhausted retries, trying fallback '%s'", primary, fallback)
        try:
            return await _complete_on_model(model=fallback, messages=messages, temperature=temperature, response_format=response_format, max_attempts=_FALLBACK_MAX_ATTEMPTS)
        except LLMServiceError as fallback_error:
            raise LLMServiceError(
                f"The AI service is temporarily unavailable on both '{primary}' and '{fallback}'. "
                "Please wait a few seconds and try again."
            ) from fallback_error


async def llm_text(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    return await _complete_with_retry(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
    )


async def llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
    """
    Calls the LLM and forces/parses a JSON object response.
    Mistral's response_format json_object mode guarantees valid JSON syntax,
    but we still guard with a manual parse + fence-strip in case of drift.
    """
    content = await _complete_with_retry(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return _safe_json_parse(content)


def _safe_json_parse(content: str) -> dict:
    cleaned = re.sub(r"^```json\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMServiceError(f"LLM did not return valid JSON: {e}\nRaw: {content[:500]}")
