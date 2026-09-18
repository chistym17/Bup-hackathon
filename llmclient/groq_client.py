import logging

from groq import Groq

from helpers.errors import InterpretationError
from helpers.logging import get_logger, log_event
from llmclient.base import LLMClient
from llmclient import config

logger = get_logger("llm.groq")


class GroqClient(LLMClient):
    name = "groq"

    def __init__(self) -> None:
        if not config.GROQ_API_KEY:
            raise InterpretationError("GROQ_API_KEY is missing", {"provider": self.name})
        self._client = Groq(api_key=config.GROQ_API_KEY, timeout=config.TIMEOUT_SECONDS)

    def complete(self, system: str, user: str) -> str:
        log_event(
            logger,
            logging.INFO,
            "groq request",
            model=config.GROQ_MODEL,
            system_chars=len(system),
            user_chars=len(user),
        )
        try:
            response = self._client.chat.completions.create(
                model=config.GROQ_MODEL,
                temperature=config.TEMPERATURE,
                max_tokens=config.MAX_OUTPUT_TOKENS,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:
            log_event(
                logger,
                logging.ERROR,
                "groq request failed",
                model=config.GROQ_MODEL,
                error=str(exc),
            )
            raise InterpretationError(
                "Groq request failed",
                {"provider": self.name, "model": config.GROQ_MODEL, "error": str(exc)},
            ) from exc

        text = (response.choices[0].message.content or "").strip()
        if not text:
            log_event(logger, logging.ERROR, "groq empty response", model=config.GROQ_MODEL)
            raise InterpretationError("Groq returned empty response", {"provider": self.name})
        log_event(
            logger,
            logging.INFO,
            "groq response",
            model=config.GROQ_MODEL,
            chars=len(text),
        )
        return text
