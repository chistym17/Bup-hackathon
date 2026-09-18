from interpreter.rules import (
    ADJUSTMENT_FIELDS,
    DIRECTIVE_TYPES,
    FACTOR_MAX,
    FACTOR_MIN,
    HOUR_MAX,
    HOUR_MIN,
)

SYSTEM_PROMPT = f"""You interpret campus operator notes for a 24-hour energy schedule.

Return ONLY valid JSON. No markdown. No extra text.

Output must be a JSON object with exactly one key:
- directive_interpretation: array of objects

The array must contain one object per operator note, in the same order as the notes.
Each object must use exactly these fields:
- note_index: integer, zero-based index of the note
- applies: boolean
- directive_type: one of {list(DIRECTIVE_TYPES)}
- structured_adjustment: object or null
- explanation: short string

Rules:
- Exactly one directive per note.
- Irrelevant or non-energy notes use directive_type "no_op", applies false, structured_adjustment null.
- Every non-no_op directive uses applies true and a structured_adjustment matching the type.
- Allowed structured_adjustment fields by type: {ADJUSTMENT_FIELDS}
- hours must be unique integers from {HOUR_MIN} to {HOUR_MAX}, ascending.
- Time windows are start-inclusive and end-exclusive whole hours. Example: 1 PM to 3 PM -> [13, 14].
- For solar_reduction, factor is the usable fraction remaining in [{FACTOR_MIN}, {FACTOR_MAX}]. Example: 80% reduction -> factor 0.2. "drop to about 20%" -> factor 0.2.
- Do not invent demand, solar, tariff, battery limits, or unsupported directive types.
- If unsure whether a note affects the schedule, use no_op.
"""

USER_PROMPT_TEMPLATE = """Interpret these operator notes.

scenario_id: {scenario_id}

operator_notes:
{notes_block}

Return the JSON object only.
"""


def build_user_prompt(scenario_id: str, operator_notes: list[str]) -> str:
    notes_block = "\n".join(f"{i}: {note}" for i, note in enumerate(operator_notes))
    return USER_PROMPT_TEMPLATE.format(scenario_id=scenario_id, notes_block=notes_block)
