import pulp

from optimizer.rules import HORIZON_HOURS, EffectiveScenario


def build_model(scenario: EffectiveScenario) -> tuple[pulp.LpProblem, dict]:
    problem = pulp.LpProblem("campus_energy", pulp.LpMinimize)

    grid = pulp.LpVariable.dicts("grid", range(HORIZON_HOURS), lowBound=0)
    solar_used = pulp.LpVariable.dicts("solar_used", range(HORIZON_HOURS), lowBound=0)
    charge = pulp.LpVariable.dicts("charge", range(HORIZON_HOURS), lowBound=0)
    discharge = pulp.LpVariable.dicts("discharge", range(HORIZON_HOURS), lowBound=0)
    energy = pulp.LpVariable.dicts("energy", range(HORIZON_HOURS), lowBound=0)
    is_charging = pulp.LpVariable.dicts("is_charging", range(HORIZON_HOURS), cat="Binary")

    problem += pulp.lpSum(
        grid[h] * scenario.tariff_bdt_per_kwh[h] for h in range(HORIZON_HOURS)
    )

    for h in range(HORIZON_HOURS):
        problem += solar_used[h] <= scenario.effective_solar_kwh[h]
        problem += (
            grid[h] + solar_used[h] + discharge[h]
            == scenario.demand_kwh[h] + charge[h]
        )

        problem += charge[h] <= scenario.max_charge_kwh_per_hour * is_charging[h]
        problem += discharge[h] <= scenario.max_discharge_kwh_per_hour * (
            1 - is_charging[h]
        )

        if h in scenario.no_charge_hours:
            problem += charge[h] == 0
            problem += is_charging[h] == 0
        if h in scenario.no_discharge_hours:
            problem += discharge[h] == 0
        if h in scenario.max_grid_by_hour:
            problem += grid[h] <= scenario.max_grid_by_hour[h]

        if h == 0:
            problem += energy[h] == scenario.initial_energy_kwh + charge[h] - discharge[h]
        else:
            problem += energy[h] == energy[h - 1] + charge[h] - discharge[h]

        problem += energy[h] >= scenario.min_energy_by_hour[h]
        problem += energy[h] <= scenario.capacity_kwh

    problem += energy[HORIZON_HOURS - 1] == scenario.initial_energy_kwh

    variables = {
        "grid": grid,
        "solar_used": solar_used,
        "charge": charge,
        "discharge": discharge,
        "energy": energy,
        "is_charging": is_charging,
    }
    return problem, variables
