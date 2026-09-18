DIRECTIVE_TYPES = (
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
)

ADJUSTMENT_FIELDS = {
    "solar_reduction": ("hours", "factor"),
    "minimum_battery_reserve": ("hours", "minimum_energy_kwh"),
    "no_charge_window": ("hours",),
    "no_discharge_window": ("hours",),
    "max_grid_window": ("hours", "max_grid_kwh"),
    "no_op": None,
}

HOUR_MIN = 0
HOUR_MAX = 23
FACTOR_MIN = 0.0
FACTOR_MAX = 1.0

TIME_WINDOW_START_INCLUSIVE = True
TIME_WINDOW_END_EXCLUSIVE = True

NO_OP_APPLIES = False
NON_NO_OP_APPLIES = True
NO_OP_ADJUSTMENT = None

NOTES_MIN = 1
NOTES_MAX = 3
