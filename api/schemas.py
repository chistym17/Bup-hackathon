from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from interpreter.schemas import DirectiveInterpretation
from optimizer.schemas import BatteryInput, HourInput, HourlyPlanEntry


class OptimizeEnergyRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    operator_notes: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1, max_length=3)
    hours: list[HourInput] = Field(min_length=24, max_length=24)
    battery: BatteryInput

    @model_validator(mode="after")
    def validate_hours(self) -> "OptimizeEnergyRequest":
        hour_ids = [entry.hour for entry in self.hours]
        if sorted(hour_ids) != list(range(24)):
            raise ValueError("hours must contain unique entries for 0..23")
        return self


class OptimizeEnergyResponse(BaseModel):
    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry]
    total_grid_kwh: float
    total_cost_bdt: float
    peak_grid_kwh: float
    plan_summary: str
