from google import genai
from google.genai import types

from helpers.errors import InterpretationError
from helpers.logging import get_logger, log_event
from llmclient.base import LLMClient
from llmclient import config
import logging

logger = get_logger("llm.gemini")


class GeminiClient(LLMClient):
    name = "gemini"

    def __init__(self) -> None:
        if not config.GEMINI_API_KEY:
            raise InterpretationError("GEMINI_API_KEY is missing", {"provider": self.name})
        self._client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.TIMEOUT_SECONDS * 1000),
        )

    def complete(self, system: str, user: str) -> str:
        log_event(
            logger,
            logging.INFO,
            "gemini request",
            model=config.GEMINI_MODEL,
            system_chars=len(system),
            user_chars=len(user),
        )
        try:
            response = self._client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    temperature=config.TEMPERATURE,
                    max_output_tokens=config.MAX_OUTPUT_TOKENS,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "gemini request failed",
                model=config.GEMINI_MODEL,
                error=str(exc),
            )
            raise InterpretationError(
                "Gemini request failed",
                {"provider": self.name, "model": config.GEMINI_MODEL, "error": str(exc)},
            ) from exc

        text = (response.text or "").strip()
        if not text:
            log_event(logger, logging.ERROR, "gemini empty response", model=config.GEMINI_MODEL)
            raise InterpretationError("Gemini returned empty response", {"provider": self.name})
        log_event(
            logger,
            logging.INFO,
            "gemini response",
            model=config.GEMINI_MODEL,
            chars=len(text),
        )
        return text
