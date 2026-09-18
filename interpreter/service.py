import logging

from helpers.errors import InterpretationError
from helpers.logging import get_logger, log_event
from interpreter.rules import NOTES_MAX, NOTES_MIN
from interpreter.schemas import DirectiveInterpretation
from interpreter.validator import DirectiveValidator
from llmclient.router import LLMRouter

logger = get_logger("interpreter.service")


class InterpreterService:
    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or LLMRouter()
        self._validator = DirectiveValidator()

    def interpret(
        self,
        scenario_id: str,
        operator_notes: list[str],
        capacity_kwh: float | None = None,
    ) -> list[DirectiveInterpretation]:
        log_event(
            logger,
            logging.INFO,
            "interpret start",
            scenario_id=scenario_id,
            note_count=len(operator_notes),
            capacity_kwh=capacity_kwh,
        )

        if not isinstance(operator_notes, list):
            raise InterpretationError(
                "operator_notes must be a list",
                {"scenario_id": scenario_id, "got": type(operator_notes).__name__},
            )
        if len(operator_notes) < NOTES_MIN or len(operator_notes) > NOTES_MAX:
            raise InterpretationError(
                "invalid operator_notes length",
                {
                    "scenario_id": scenario_id,
                    "count": len(operator_notes),
                    "min": NOTES_MIN,
                    "max": NOTES_MAX,
                },
            )
        for index, note in enumerate(operator_notes):
            if not isinstance(note, str) or not note.strip():
                raise InterpretationError(
                    "operator note must be a non-empty string",
                    {"scenario_id": scenario_id, "note_index": index},
                )

        try:
            raw = self._router.interpret_notes(scenario_id, operator_notes)
        except InterpretationError as exc:
            log_event(
                logger,
                logging.ERROR,
                "llm interpret failed",
                scenario_id=scenario_id,
                code=exc.code,
                details=exc.details,
            )
            raise

        log_event(
            logger,
            logging.INFO,
            "llm raw received",
            scenario_id=scenario_id,
            chars=len(raw),
        )

        try:
            validated = self._validator.validate(
                raw,
                operator_notes,
                capacity_kwh=capacity_kwh,
            )
        except InterpretationError as exc:
            log_event(
                logger,
                logging.ERROR,
                "directive validation failed",
                scenario_id=scenario_id,
                code=exc.code,
                details=exc.details,
                raw=raw[:500],
            )
            raise

        log_event(
            logger,
            logging.INFO,
            "interpret success",
            scenario_id=scenario_id,
            directives=[
                {
                    "note_index": entry.note_index,
                    "applies": entry.applies,
                    "directive_type": entry.directive_type,
                    "structured_adjustment": entry.structured_adjustment,
                }
                for entry in validated
            ],
        )
        return validated
