import json
import logging
import math
from typing import Any

from helpers.errors import InterpretationError
from helpers.logging import get_logger, log_event
from interpreter.rules import (
    ADJUSTMENT_FIELDS,
    FACTOR_MAX,
    FACTOR_MIN,
    HOUR_MAX,
    HOUR_MIN,
    NOTES_MAX,
    NOTES_MIN,
)
from interpreter.schemas import DirectiveInterpretation

logger = get_logger("interpreter.validator")


class DirectiveValidator:
    def validate(
        self,
        raw_text: str,
        operator_notes: list[str],
        capacity_kwh: float | None = None,
    ) -> list[DirectiveInterpretation]:
        note_count = len(operator_notes)
        if note_count < NOTES_MIN or note_count > NOTES_MAX:
            raise InterpretationError(
                "invalid operator_notes length",
                {"count": note_count, "min": NOTES_MIN, "max": NOTES_MAX},
            )

        log_event(logger, logging.INFO, "validation start", note_count=note_count)
        items = self._parse_items(raw_text)

        indexed: dict[int, Any] = {}
        for position, item in enumerate(items):
            index = item.get("note_index") if isinstance(item, dict) else None
            if not isinstance(index, int) or not 0 <= index < note_count:
                index = position
            indexed.setdefault(index, item)

        validated: list[DirectiveInterpretation] = []
        for expected_index in range(note_count):
            item = indexed.get(expected_index)
            try:
                if item is None:
                    raise InterpretationError(
                        "missing interpretation entry",
                        {"note_index": expected_index},
                    )
                validated.append(
                    self._validate_item(item, expected_index, capacity_kwh=capacity_kwh)
                )
            except InterpretationError as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "note fell back to no_op",
                    note_index=expected_index,
                    reason=exc.message,
                    details=exc.details,
                )
                validated.append(self._no_op(expected_index))

        log_event(
            logger,
            logging.INFO,
            "directives validated",
            count=len(validated),
            types=[entry.directive_type for entry in validated],
            applies=[entry.applies for entry in validated],
        )
        return validated

    def _no_op(self, note_index: int) -> DirectiveInterpretation:
        return DirectiveInterpretation(
            note_index=note_index,
            applies=False,
            directive_type="no_op",
            structured_adjustment=None,
            explanation="This note does not change the 24-hour energy schedule.",
        )

    def _parse_items(self, raw_text: str) -> list[Any]:
        text = raw_text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            log_event(
                logger,
                logging.ERROR,
                "llm returned invalid json",
                error=str(exc),
                raw=raw_text[:500],
            )
            return []

        if isinstance(data, dict):
            data = data.get("directive_interpretation")
        if not isinstance(data, list):
            log_event(logger, logging.ERROR, "llm payload missing directive list")
            return []
        return data

    def _validate_item(
        self,
        item: Any,
        expected_index: int,
        capacity_kwh: float | None,
    ) -> DirectiveInterpretation:
        if not isinstance(item, dict):
            raise InterpretationError(
                "interpretation entry must be an object",
                {"note_index": expected_index, "got": type(item).__name__},
            )

        try:
            entry = DirectiveInterpretation.model_validate({**item, "note_index": expected_index})
        except Exception as exc:
            raise InterpretationError(
                "interpretation entry schema invalid",
                {"note_index": expected_index, "error": str(exc)},
            ) from exc

        if entry.directive_type == "no_op":
            return entry.model_copy(update={"applies": False, "structured_adjustment": None})

        required = ADJUSTMENT_FIELDS[entry.directive_type]
        adjustment = entry.structured_adjustment
        if not isinstance(adjustment, dict):
            raise InterpretationError(
                "structured_adjustment must be an object",
                {"note_index": expected_index, "directive_type": entry.directive_type},
            )
        missing = [field for field in required if field not in adjustment]
        if missing:
            raise InterpretationError(
                "structured_adjustment missing fields",
                {
                    "note_index": expected_index,
                    "directive_type": entry.directive_type,
                    "missing": missing,
                },
            )

        normalized: dict[str, Any] = {
            "hours": self._validate_hours(adjustment["hours"], expected_index)
        }

        if entry.directive_type == "solar_reduction":
            factor = self._number(adjustment["factor"], "factor", expected_index)
            if not FACTOR_MIN <= factor <= FACTOR_MAX:
                raise InterpretationError(
                    "factor out of range",
                    {"note_index": expected_index, "factor": factor},
                )
            normalized["factor"] = factor

        if entry.directive_type == "minimum_battery_reserve":
            reserve = self._number(
                adjustment["minimum_energy_kwh"],
                "minimum_energy_kwh",
                expected_index,
            )
            if reserve < 0:
                raise InterpretationError(
                    "minimum_energy_kwh must be non-negative",
                    {"note_index": expected_index, "value": reserve},
                )
            if capacity_kwh is not None and reserve > float(capacity_kwh):
                raise InterpretationError(
                    "minimum_energy_kwh exceeds capacity",
                    {
                        "note_index": expected_index,
                        "value": reserve,
                        "capacity_kwh": capacity_kwh,
                    },
                )
            normalized["minimum_energy_kwh"] = reserve

        if entry.directive_type == "max_grid_window":
            cap = self._number(adjustment["max_grid_kwh"], "max_grid_kwh", expected_index)
            if cap < 0:
                raise InterpretationError(
                    "max_grid_kwh must be non-negative",
                    {"note_index": expected_index, "value": cap},
                )
            normalized["max_grid_kwh"] = cap

        return entry.model_copy(
            update={"applies": True, "structured_adjustment": normalized}
        )

    def _number(self, value: Any, name: str, note_index: int) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InterpretationError(
                f"{name} must be a number",
                {"note_index": note_index, "value": value},
            )
        number = float(value)
        if not math.isfinite(number):
            raise InterpretationError(
                f"{name} must be finite",
                {"note_index": note_index, "value": value},
            )
        return number

    def _validate_hours(self, hours: Any, note_index: int) -> list[int]:
        if not isinstance(hours, list) or not hours:
            raise InterpretationError(
                "hours must be a non-empty list",
                {"note_index": note_index, "hours": hours},
            )

        normalized: list[int] = []
        for hour in hours:
            if isinstance(hour, bool):
                raise InterpretationError(
                    "hours must be integers",
                    {"note_index": note_index, "hours": hours},
                )
            if isinstance(hour, float) and hour.is_integer():
                hour = int(hour)
            if not isinstance(hour, int):
                raise InterpretationError(
                    "hours must be integers",
                    {"note_index": note_index, "hours": hours},
                )
            if hour < HOUR_MIN or hour > HOUR_MAX:
                raise InterpretationError(
                    "hour out of range",
                    {"note_index": note_index, "hour": hour},
                )
            normalized.append(hour)

        unique = sorted(set(normalized))
        if unique != normalized:
            log_event(
                logger,
                logging.WARNING,
                "hours normalized to unique ascending",
                note_index=note_index,
                original=normalized,
                normalized=unique,
            )
        return unique
