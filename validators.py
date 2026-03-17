"""
Pure validation functions — no tkinter dependency.
Each function returns (is_valid: bool, error_msg: str, parsed_value).
"""


def parse_retraction(raw):
    """Validate retraction distance string. Returns (bool, str, float)."""
    if not raw:
        return False, "Retraction distance is required.", 0.0
    try:
        value = float(raw)
    except ValueError:
        return False, "Must be a number (e.g. 3.5).", 0.0
    if value <= 0 or value > 50:
        return False, "Value must be between 0.1 and 50.", value
    if raw.count('.') > 1:
        return False, "Only one decimal point allowed.", value
    if '.' in raw:
        decimals = raw.split('.')[1]
        if len(decimals) > 1:
            return False, "Maximum 1 decimal place.", value
    return True, "", value


def parse_wipe_distance(raw):
    """Validate wipe distance string. Returns (bool, str, float)."""
    if not raw:
        return False, "Wipe distance is required.", 0.0
    try:
        value = float(raw)
    except ValueError:
        return False, "Must be a number (e.g. 5).", 0.0
    if value <= 0 or value > 50:
        return False, "Value must be between 0.1 and 50.", value
    return True, "", value


def parse_dwell_time(raw):
    """Validate dwell time string. Returns (bool, str, int)."""
    if not raw:
        return False, "Dwell time is required.", 0
    try:
        value = float(raw)
    except ValueError:
        return False, "Must be a whole number (e.g. 3).", 0
    value = int(round(value))
    if value <= 0 or value > 60:
        return False, "Value must be between 1 and 60 seconds.", value
    return True, "", value


def parse_temperature(raw, field_name):
    """Validate temperature string. Returns (bool, str, int)."""
    if not raw:
        return False, f"{field_name} is required.", 0
    try:
        value = float(raw)
    except ValueError:
        return False, f"{field_name} must be a number.", 0
    value = int(round(value))
    if value <= 0 or value > 400:
        return False, f"{field_name} must be between 1 and 400°C.", value
    return True, "", value
