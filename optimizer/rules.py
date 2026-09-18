from dataclasses import dataclass
import logging
import math

from helpers.errors import OptimizationError
from helpers.logging import get_logger, log_event
from interpreter.schemas import DirectiveInterpretation

logger = get_logger("optimizer.rules")

HORIZON_HOURS = 24
NUMERIC_TOLERANCE = 0.01
SOLVER_EPSILON = 1e-6
BATTERY_ACTIONS = ("charge", "discharge", "idle")


@dataclass(frozen=True)
class EffectiveScenario:
    demand_kwh: list[float]
    effective_solar_kwh: list[float]
    tariff_bdt_per_kwh: list[float]
    capacity_kwh: float
    initial_energy_kwh: float
    minimum_energy_kwh: float
    max_charge_kwh_per_hour: float
    max_discharge_kwh_per_hour: float
    min_energy_by_hour: list[float]
    no_charge_hours: frozenset[int]
    no_discharge_hours: frozenset[int]
    max_grid_by_hour: dict[int, float]


def _require_finite_non_negative(name: str, value: float) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise OptimizationError(
            f"{name} must be finite and non-negative",
            {"name": name, "value": value},
        )
    return number


def build_effective_scenario(
    hours: list[dict],
    battery: dict,
    directives: list[DirectiveInterpretation],
) -> EffectiveScenario:
    by_hour = sorted(hours, key=lambda item: item["hour"])
    if len(by_hour) != HORIZON_HOURS:
        raise OptimizationError(
            "hours must contain exactly 24 entries",
            {"count": len(by_hour)},
        )
    if [item["hour"] for item in by_hour] != list(range(HORIZON_HOURS)):
        raise OptimizationError("hours must cover 0..23 uniquely")

    demand = [_require_finite_non_negative("demand_kwh", item["demand_kwh"]) for item in by_hour]
    solar = [_require_finite_non_negative("solar_kwh", item["solar_kwh"]) for item in by_hour]
    tariff = [
        _require_finite_non_negative("tariff_bdt_per_kwh", item["tariff_bdt_per_kwh"])
        for item in by_hour
    ]
    effective_solar = list(solar)

    capacity = _require_finite_non_negative("capacity_kwh", battery["capacity_kwh"])
    initial = _require_finite_non_negative("initial_energy_kwh", battery["initial_energy_kwh"])
    base_min = _require_finite_non_negative("minimum_energy_kwh", battery["minimum_energy_kwh"])
    max_charge = _require_finite_non_negative(
        "max_charge_kwh_per_hour",
        battery["max_charge_kwh_per_hour"],
    )
    max_discharge = _require_finite_non_negative(
        "max_discharge_kwh_per_hour",
        battery["max_discharge_kwh_per_hour"],
    )

    if base_min > capacity:
        raise OptimizationError(
            "minimum_energy_kwh exceeds capacity_kwh",
            {"minimum_energy_kwh": base_min, "capacity_kwh": capacity},
        )
    if initial < base_min or initial > capacity:
        raise OptimizationError(
            "initial_energy_kwh out of battery bounds",
            {
                "initial_energy_kwh": initial,
                "minimum_energy_kwh": base_min,
                "capacity_kwh": capacity,
            },
        )

    min_energy_by_hour = [base_min] * HORIZON_HOURS
    no_charge: set[int] = set()
    no_discharge: set[int] = set()
    max_grid: dict[int, float] = {}
    applied: list[str] = []

    for directive in directives:
        if not directive.applies or directive.directive_type == "no_op":
            continue
        adjustment = directive.structured_adjustment or {}
        hours_list = [int(h) for h in adjustment["hours"]]
        applied.append(directive.directive_type)

        if directive.directive_type == "solar_reduction":
            factor = float(adjustment["factor"])
            for hour in hours_list:
                effective_solar[hour] = effective_solar[hour] * factor
        elif directive.directive_type == "minimum_battery_reserve":
            reserve = float(adjustment["minimum_energy_kwh"])
            for hour in hours_list:
                min_energy_by_hour[hour] = max(min_energy_by_hour[hour], reserve)
        elif directive.directive_type == "no_charge_window":
            no_charge.update(hours_list)
        elif directive.directive_type == "no_discharge_window":
            no_discharge.update(hours_list)
        elif directive.directive_type == "max_grid_window":
            cap = float(adjustment["max_grid_kwh"])
            for hour in hours_list:
                if hour in max_grid:
                    max_grid[hour] = min(max_grid[hour], cap)
                else:
                    max_grid[hour] = cap
        else:
            raise OptimizationError(
                "unsupported directive in optimizer",
                {"directive_type": directive.directive_type},
            )

    scenario = EffectiveScenario(
        demand_kwh=demand,
        effective_solar_kwh=effective_solar,
        tariff_bdt_per_kwh=tariff,
        capacity_kwh=capacity,
        initial_energy_kwh=initial,
        minimum_energy_kwh=base_min,
        max_charge_kwh_per_hour=max_charge,
        max_discharge_kwh_per_hour=max_discharge,
        min_energy_by_hour=min_energy_by_hour,
        no_charge_hours=frozenset(no_charge),
        no_discharge_hours=frozenset(no_discharge),
        max_grid_by_hour=max_grid,
    )
    log_event(
        logger,
        logging.INFO,
        "effective scenario ready",
        applied_directives=applied,
        no_charge_hours=sorted(no_charge),
        no_discharge_hours=sorted(no_discharge),
        max_grid_hours=sorted(max_grid.keys()),
        raised_reserve_hours=[
            h for h in range(HORIZON_HOURS) if min_energy_by_hour[h] > base_min + NUMERIC_TOLERANCE
        ],
    )
    return scenario
