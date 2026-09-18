import logging

from api.schemas import OptimizeEnergyRequest, OptimizeEnergyResponse
from helpers.logging import get_logger, log_event
from interpreter.service import InterpreterService
from optimizer.solver import solve

logger = get_logger("api.service")


class EnergyOptimizeService:
    def __init__(self) -> None:
        self._interpreter = InterpreterService()

    def run(self, request: OptimizeEnergyRequest) -> OptimizeEnergyResponse:
        log_event(
            logger,
            logging.INFO,
            "optimize-energy start",
            scenario_id=request.scenario_id,
            note_count=len(request.operator_notes),
        )

        directives = self._interpreter.interpret(
            request.scenario_id,
            request.operator_notes,
            capacity_kwh=request.battery.capacity_kwh,
        )

        hours = [entry.model_dump() for entry in request.hours]
        battery = request.battery.model_dump()
        result = solve(hours, battery, directives)

        response = OptimizeEnergyResponse(
            scenario_id=request.scenario_id,
            directive_interpretation=directives,
            hourly_plan=result.hourly_plan,
            total_grid_kwh=result.total_grid_kwh,
            total_cost_bdt=result.total_cost_bdt,
            peak_grid_kwh=result.peak_grid_kwh,
            plan_summary=result.plan_summary,
        )
        log_event(
            logger,
            logging.INFO,
            "optimize-energy success",
            scenario_id=request.scenario_id,
            total_cost_bdt=response.total_cost_bdt,
            total_grid_kwh=response.total_grid_kwh,
            peak_grid_kwh=response.peak_grid_kwh,
        )
        return response
