from typing import Any, Literal

from pydantic import BaseModel, Field

from interpreter.rules import DIRECTIVE_TYPES

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]


class DirectiveInterpretation(BaseModel):
    note_index: int
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: dict[str, Any] | None
    explanation: str = Field(min_length=1)


assert set(DIRECTIVE_TYPES) == set(DirectiveType.__args__)
