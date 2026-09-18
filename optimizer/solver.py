import logging

import pulp

from helpers.errors import OptimizationError
from helpers.logging import get_logger, log_event
from interpreter.schemas import DirectiveInterpretation
from optimizer.model import build_model
from optimizer.replay import replay_plan
from optimizer.rules import (
    HORIZON_HOURS,
    SOLVER_EPSILON,
    EffectiveScenario,
    build_effective_scenario,
)
from optimizer.schemas import HourlyPlanEntry, OptimizeResult

logger = get_logger("optimizer.solver")


def _clean(var: pulp.LpVariable) -> float:
    raw = pulp.value(var)
    if raw is None or abs(raw) < SOLVER_EPSILON:
        return 0.0
    return float(raw)


def _extract_plan(
    variables: dict,
    scenario: EffectiveScenario,
    summary: str,
) -> OptimizeResult:
    hourly_plan: list[HourlyPlanEntry] = []
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0
    energy = scenario.initial_energy_kwh

    for h in range(HORIZON_HOURS):
        charge = _clean(variables["charge"][h])
        discharge = _clean(variables["discharge"][h])
        if charge > 0 and discharge > 0:
            raise OptimizationError(
                "solver produced simultaneous charge and discharge",
                {"hour": h, "charge": charge, "discharge": discharge},
            )

        energy = energy + charge - discharge
        solar_used = min(_clean(variables["solar_used"][h]), scenario.effective_solar_kwh[h])
        grid = scenario.demand_kwh[h] + charge - solar_used - discharge
        if grid < 0:
            solar_used += grid
            grid = 0.0

        if charge > 0:
            action = "charge"
            battery_kwh = charge
        elif discharge > 0:
            action = "discharge"
            battery_kwh = discharge
        else:
            action = "idle"
            battery_kwh = 0.0

        hourly_plan.append(
            HourlyPlanEntry(
                hour=h,
                grid_kwh=round(grid, 6),
                solar_used_kwh=round(solar_used, 6),
                battery_action=action,
                battery_kwh=round(battery_kwh, 6),
                battery_energy_after_kwh=round(energy, 6),
            )
        )
        total_grid += grid
        total_cost += grid * scenario.tariff_bdt_per_kwh[h]
        peak_grid = max(peak_grid, grid)

    return OptimizeResult(
        hourly_plan=hourly_plan,
        total_grid_kwh=round(total_grid, 6),
        total_cost_bdt=round(total_cost, 6),
        peak_grid_kwh=round(peak_grid, 6),
        plan_summary=summary,
    )


def _build_summary(
    scenario: EffectiveScenario,
    directives: list[DirectiveInterpretation],
) -> str:
    applied = [d.directive_type for d in directives if d.applies and d.directive_type != "no_op"]
    directive_text = ", ".join(sorted(set(applied))) if applied else "none"
    return (
        "Used available solar first, charged the battery in the cheapest hours and discharged it "
        "during peak tariff hours, returning the battery to its starting level. "
        f"Applied operator directives: {directive_text}."
    )


def solve(
    hours: list[dict],
    battery: dict,
    directives: list[DirectiveInterpretation],
) -> OptimizeResult:
    log_event(logger, logging.INFO, "optimize start", directive_count=len(directives))

    try:
        scenario = build_effective_scenario(hours, battery, directives)
    except OptimizationError as exc:
        log_event(
            logger,
            logging.ERROR,
            "effective scenario failed",
            code=exc.code,
            details=exc.details,
        )
        raise

    problem, variables = build_model(scenario)

    try:
        status = problem.solve(pulp.PULP_CBC_CMD(msg=False))
    except Exception as exc:
        log_event(logger, logging.ERROR, "cbc crashed", error=str(exc))
        raise OptimizationError("cbc solver crashed", {"error": str(exc)}) from exc

    status_name = pulp.LpStatus.get(status, str(status))
    log_event(logger, logging.INFO, "cbc finished", status=status_name)

    if status != pulp.LpStatusOptimal:
        log_event(logger, logging.ERROR, "cbc not optimal", status=status_name)
        raise OptimizationError(
            "optimizer failed to find optimal schedule",
            {"status": status_name},
        )

    try:
        result = _extract_plan(variables, scenario, _build_summary(scenario, directives))
    except OptimizationError as exc:
        log_event(
            logger,
            logging.ERROR,
            "plan extraction failed",
            code=exc.code,
            details=exc.details,
        )
        raise

    try:
        replay_plan(result.hourly_plan, hours, battery, directives, result)
    except OptimizationError as exc:
        log_event(
            logger,
            logging.ERROR,
            "replay failed after solve",
            code=exc.code,
            details=exc.details,
        )
        raise

    log_event(
        logger,
        logging.INFO,
        "optimize success",
        total_cost_bdt=result.total_cost_bdt,
        total_grid_kwh=result.total_grid_kwh,
        peak_grid_kwh=result.peak_grid_kwh,
    )
    return result
