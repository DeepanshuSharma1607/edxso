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
_BASE_DELAY_SECONDS = 2.0

class LLMServiceError(RuntimeError):
    """Raised when the LLM call fails after retries or non-transiently."""
    pass

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not getattr(settings, "gemini_api_key", None):
            # Fallback to standard environment variable if not in settings
            import os
            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError("GEMINI_API_KEY is not set.")
            _client = genai.Client(api_key=api_key)
        else:
            _client = genai.Client(api_key=settings.gemini_api_key)
    return _client

async def _complete_with_retry(
    *, 
    system_prompt: str, 
    user_prompt: str, 
    temperature: float, 
    response_mime_type: str = "text/plain"
) -> str:
    client = _get_client()
    model = getattr(settings, "gemini_model", "gemini-2.5-flash")

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        response_mime_type=response_mime_type,
    )

    last_error = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            # Using asyncio.to_thread since standard API call is synchronous
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model,
                contents=user_prompt,
                config=config,
            )
            return response.text
        except APIError as e:
            last_error = e
            status_code = getattr(e, "code", None)
            if status_code not in _RETRYABLE_STATUS_CODES:
                raise LLMServiceError(f"Gemini API rejected request ({status_code}): {e}") from e
            
            if attempt == _MAX_ATTEMPTS:
                raise LLMServiceError(f"Gemini service unavailable after {attempt} attempts: {e}") from e
            
            delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            await asyncio.sleep(delay)
        except Exception as e:
            raise LLMServiceError(f"Gemini call failed: {e}") from e

    raise LLMServiceError(f"Gemini call failed: {last_error}")

async def llm_text(system_prompt: str, user_prompt: str, temperature: float = 0.4) -> str:
    return await _complete_with_retry(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        response_mime_type="text/plain"
    )

async def llm_json(system_prompt: str, user_prompt: str, temperature: float = 0.3) -> dict:
    content = await _complete_with_retry(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        response_mime_type="application/json"
    )
    return _safe_json_parse(content)

def _safe_json_parse(content: str) -> dict:
    cleaned = re.sub(r"^```json\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise LLMServiceError(f"LLM did not return valid JSON: {e}\nRaw: {content[:500]}")
