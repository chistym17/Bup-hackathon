import logging

from helpers.errors import InterpretationError
from helpers.logging import get_logger, log_event
from llmclient import config
from llmclient.gemini_client import GeminiClient
from llmclient.groq_client import GroqClient
from llmclient.prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger("llm.router")


class LLMRouter:
    def __init__(self) -> None:
        self._gemini: GeminiClient | None = None
        self._groq: GroqClient | None = None

    def _get_gemini(self) -> GeminiClient:
        if self._gemini is None:
            self._gemini = GeminiClient()
        return self._gemini

    def _get_groq(self) -> GroqClient:
        if self._groq is None:
            self._groq = GroqClient()
        return self._groq

    def complete(self, system: str, user: str) -> str:
        groq_error: Exception | None = None
        gemini_error: Exception | None = None

        if config.GROQ_API_KEY:
            try:
                text = self._get_groq().complete(system, user)
                log_event(logger, logging.INFO, "llm complete", provider="groq")
                return text
            except Exception as exc:
                groq_error = exc
                log_event(
                    logger,
                    logging.WARNING,
                    "groq failed, trying gemini",
                    error=str(exc),
                )
        else:
            log_event(logger, logging.WARNING, "groq skipped, missing api key")

        if config.GEMINI_API_KEY:
            try:
                text = self._get_gemini().complete(system, user)
                log_event(logger, logging.INFO, "llm complete", provider="gemini", fallback=True)
                return text
            except Exception as exc:
                gemini_error = exc
                log_event(
                    logger,
                    logging.ERROR,
                    "gemini fallback failed",
                    error=str(exc),
                )
        else:
            log_event(logger, logging.WARNING, "gemini skipped, missing api key")

        log_event(
            logger,
            logging.ERROR,
            "all llm providers failed",
            groq_error=str(groq_error) if groq_error else "unavailable",
            gemini_error=str(gemini_error) if gemini_error else "unavailable",
        )
        raise InterpretationError(
            "Groq and Gemini both failed",
            {
                "groq_error": str(groq_error) if groq_error else "unavailable",
                "gemini_error": str(gemini_error) if gemini_error else "unavailable",
            },
        )

    def interpret_notes(self, scenario_id: str, operator_notes: list[str]) -> str:
        log_event(
            logger,
            logging.INFO,
            "interpret_notes request",
            scenario_id=scenario_id,
            note_count=len(operator_notes),
        )
        return self.complete(SYSTEM_PROMPT, build_user_prompt(scenario_id, operator_notes))
