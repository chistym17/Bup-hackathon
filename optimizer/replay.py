import logging
import math

from helpers.errors import OptimizationError
from helpers.logging import get_logger, log_event
from interpreter.schemas import DirectiveInterpretation
from optimizer.rules import (
    HORIZON_HOURS,
    NUMERIC_TOLERANCE,
    build_effective_scenario,
)
from optimizer.schemas import HourlyPlanEntry, OptimizeResult

logger = get_logger("optimizer.replay")


def _near(left: float, right: float) -> bool:
    return abs(left - right) <= NUMERIC_TOLERANCE


def _finite_non_negative(value: float) -> bool:
    return math.isfinite(value) and value >= -NUMERIC_TOLERANCE


def replay_plan(
    hourly_plan: list[HourlyPlanEntry],
    hours: list[dict],
    battery: dict,
    directives: list[DirectiveInterpretation],
    totals: OptimizeResult | None = None,
) -> None:
    log_event(logger, logging.INFO, "replay start")
    try:
        _replay_plan(hourly_plan, hours, battery, directives, totals)
    except OptimizationError as exc:
        log_event(
            logger,
            logging.ERROR,
            "replay failed",
            code=exc.code,
            details=exc.details,
        )
        raise


def _replay_plan(
    hourly_plan: list[HourlyPlanEntry],
    hours: list[dict],
    battery: dict,
    directives: list[DirectiveInterpretation],
    totals: OptimizeResult | None = None,
) -> None:
    scenario = build_effective_scenario(hours, battery, directives)

    if len(hourly_plan) != HORIZON_HOURS:
        raise OptimizationError(
            "hourly_plan must contain 24 entries",
            {"count": len(hourly_plan)},
        )

    sorted_plan = sorted(hourly_plan, key=lambda item: item.hour)
    if [item.hour for item in sorted_plan] != list(range(HORIZON_HOURS)):
        raise OptimizationError("hourly_plan hours must be unique 0..23")

    energy_before = scenario.initial_energy_kwh
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for entry in sorted_plan:
        h = entry.hour
        grid = float(entry.grid_kwh)
        solar_used = float(entry.solar_used_kwh)
        battery_kwh = float(entry.battery_kwh)
        energy_after = float(entry.battery_energy_after_kwh)
        action = entry.battery_action

        if not _finite_non_negative(grid):
            raise OptimizationError("grid_kwh invalid", {"hour": h, "grid_kwh": grid})
        if not _finite_non_negative(solar_used):
            raise OptimizationError(
                "solar_used_kwh invalid",
                {"hour": h, "solar_used_kwh": solar_used},
            )
        if not _finite_non_negative(battery_kwh):
            raise OptimizationError(
                "battery_kwh invalid",
                {"hour": h, "battery_kwh": battery_kwh},
            )
        if not math.isfinite(energy_after):
            raise OptimizationError(
                "battery_energy_after_kwh invalid",
                {"hour": h, "battery_energy_after_kwh": energy_after},
            )

        if solar_used - scenario.effective_solar_kwh[h] > NUMERIC_TOLERANCE:
            raise OptimizationError(
                "solar_used exceeds effective solar",
                {
                    "hour": h,
                    "solar_used_kwh": solar_used,
                    "effective_solar_kwh": scenario.effective_solar_kwh[h],
                },
            )

        if action == "charge":
            charge = battery_kwh
            discharge = 0.0
            expected_energy = energy_before + charge
            if battery_kwh - scenario.max_charge_kwh_per_hour > NUMERIC_TOLERANCE:
                raise OptimizationError(
                    "charge exceeds max_charge_kwh_per_hour",
                    {"hour": h, "battery_kwh": battery_kwh},
                )
            if h in scenario.no_charge_hours and battery_kwh > NUMERIC_TOLERANCE:
                raise OptimizationError("charge in no_charge_window", {"hour": h})
        elif action == "discharge":
            charge = 0.0
            discharge = battery_kwh
            expected_energy = energy_before - discharge
            if battery_kwh - scenario.max_discharge_kwh_per_hour > NUMERIC_TOLERANCE:
                raise OptimizationError(
                    "discharge exceeds max_discharge_kwh_per_hour",
                    {"hour": h, "battery_kwh": battery_kwh},
                )
            if h in scenario.no_discharge_hours and battery_kwh > NUMERIC_TOLERANCE:
                raise OptimizationError("discharge in no_discharge_window", {"hour": h})
        elif action == "idle":
            charge = 0.0
            discharge = 0.0
            expected_energy = energy_before
            if battery_kwh > NUMERIC_TOLERANCE:
                raise OptimizationError("idle requires battery_kwh=0", {"hour": h})
        else:
            raise OptimizationError("invalid battery_action", {"hour": h, "action": action})

        if abs((grid + solar_used + discharge) - (scenario.demand_kwh[h] + charge)) > NUMERIC_TOLERANCE:
            raise OptimizationError(
                "energy balance violated",
                {
                    "hour": h,
                    "lhs": grid + solar_used + discharge,
                    "rhs": scenario.demand_kwh[h] + charge,
                },
            )

        if not _near(energy_after, expected_energy):
            raise OptimizationError(
                "battery transition invalid",
                {
                    "hour": h,
                    "expected": expected_energy,
                    "got": energy_after,
                },
            )

        if energy_after + NUMERIC_TOLERANCE < scenario.min_energy_by_hour[h]:
            raise OptimizationError(
                "battery below required reserve",
                {
                    "hour": h,
                    "energy_after": energy_after,
                    "minimum": scenario.min_energy_by_hour[h],
                },
            )
        if energy_after - scenario.capacity_kwh > NUMERIC_TOLERANCE:
            raise OptimizationError(
                "battery above capacity",
                {"hour": h, "energy_after": energy_after},
            )

        if h in scenario.max_grid_by_hour and grid - scenario.max_grid_by_hour[h] > NUMERIC_TOLERANCE:
            raise OptimizationError(
                "grid exceeds max_grid_window",
                {
                    "hour": h,
                    "grid_kwh": grid,
                    "max_grid_kwh": scenario.max_grid_by_hour[h],
                },
            )

        energy_before = energy_after
        total_grid += grid
        total_cost += grid * scenario.tariff_bdt_per_kwh[h]
        peak_grid = max(peak_grid, grid)

    if not _near(energy_before, scenario.initial_energy_kwh):
        raise OptimizationError(
            "end-of-day battery neutrality violated",
            {
                "final_energy": energy_before,
                "initial_energy": scenario.initial_energy_kwh,
            },
        )

    if totals is not None:
        if not _near(totals.total_grid_kwh, total_grid):
            raise OptimizationError(
                "total_grid_kwh mismatch",
                {"reported": totals.total_grid_kwh, "recomputed": total_grid},
            )
        if not _near(totals.total_cost_bdt, total_cost):
            raise OptimizationError(
                "total_cost_bdt mismatch",
                {"reported": totals.total_cost_bdt, "recomputed": total_cost},
            )
        if not _near(totals.peak_grid_kwh, peak_grid):
            raise OptimizationError(
                "peak_grid_kwh mismatch",
                {"reported": totals.peak_grid_kwh, "recomputed": peak_grid},
            )

    log_event(
        logger,
        logging.INFO,
        "replay success",
        total_cost_bdt=total_cost,
        total_grid_kwh=total_grid,
        peak_grid_kwh=peak_grid,
    )
