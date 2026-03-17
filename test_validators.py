"""
Unit tests for validators.py
Run with: pytest test_validators.py -v
"""
import pytest

from validators import (
    parse_retraction,
    parse_wipe_distance,
    parse_dwell_time,
    parse_temperature,
)


# ── parse_retraction ──────────────────────────────────────────────────────────

class TestParseRetraction:
    def test_empty_string(self):
        ok, _, v = parse_retraction("")
        assert not ok
        assert v == 0.0

    def test_non_numeric(self):
        ok, _, _ = parse_retraction("abc")
        assert not ok

    def test_zero(self):
        ok, _, _ = parse_retraction("0")
        assert not ok

    def test_negative(self):
        ok, _, _ = parse_retraction("-1")
        assert not ok

    def test_above_max(self):
        ok, _, _ = parse_retraction("51")
        assert not ok

    def test_valid_float(self):
        ok, _, v = parse_retraction("3.5")
        assert ok
        assert v == 3.5

    def test_valid_integer_string(self):
        ok, _, v = parse_retraction("5")
        assert ok
        assert v == 5.0

    def test_valid_max(self):
        ok, _, v = parse_retraction("50")
        assert ok
        assert v == 50.0

    def test_valid_min(self):
        ok, _, v = parse_retraction("0.1")
        assert ok

    def test_two_decimal_points_rejected(self):
        ok, _, _ = parse_retraction("3.5.5")
        assert not ok

    def test_more_than_one_decimal_place_rejected(self):
        ok, _, _ = parse_retraction("3.55")
        assert not ok

    def test_exactly_one_decimal_place_allowed(self):
        ok, _, v = parse_retraction("3.5")
        assert ok
        assert v == 3.5

    def test_trailing_dot_allowed(self):
        # "3." has 0 decimal digits — passes the 1-decimal check
        ok, _, v = parse_retraction("3.")
        assert ok
        assert v == 3.0

    def test_error_message_non_numeric(self):
        ok, msg, _ = parse_retraction("xyz")
        assert not ok
        assert "number" in msg.lower()

    def test_error_message_empty(self):
        ok, msg, _ = parse_retraction("")
        assert not ok
        assert "required" in msg.lower()


# ── parse_wipe_distance ───────────────────────────────────────────────────────

class TestParseWipeDistance:
    def test_empty_string(self):
        ok, _, _ = parse_wipe_distance("")
        assert not ok

    def test_non_numeric(self):
        ok, _, _ = parse_wipe_distance("xyz")
        assert not ok

    def test_zero(self):
        ok, _, _ = parse_wipe_distance("0")
        assert not ok

    def test_negative(self):
        ok, _, _ = parse_wipe_distance("-5")
        assert not ok

    def test_above_max(self):
        ok, _, _ = parse_wipe_distance("51")
        assert not ok

    def test_valid_integer(self):
        ok, _, v = parse_wipe_distance("5")
        assert ok
        assert v == 5.0

    def test_valid_float(self):
        ok, _, v = parse_wipe_distance("12.5")
        assert ok
        assert v == 12.5

    def test_valid_max(self):
        ok, _, v = parse_wipe_distance("50")
        assert ok

    def test_multiple_decimal_places_accepted(self):
        # wipe_distance has no 1-decimal restriction
        ok, _, v = parse_wipe_distance("5.25")
        assert ok
        assert v == 5.25

    def test_error_message_empty(self):
        ok, msg, _ = parse_wipe_distance("")
        assert not ok
        assert "required" in msg.lower()


# ── parse_dwell_time ──────────────────────────────────────────────────────────

class TestParseDwellTime:
    def test_empty_string(self):
        ok, _, _ = parse_dwell_time("")
        assert not ok

    def test_non_numeric(self):
        ok, _, _ = parse_dwell_time("abc")
        assert not ok

    def test_zero(self):
        ok, _, _ = parse_dwell_time("0")
        assert not ok

    def test_negative(self):
        ok, _, _ = parse_dwell_time("-1")
        assert not ok

    def test_above_max(self):
        ok, _, _ = parse_dwell_time("61")
        assert not ok

    def test_valid_integer(self):
        ok, _, v = parse_dwell_time("3")
        assert ok
        assert v == 3

    def test_valid_max(self):
        ok, _, v = parse_dwell_time("60")
        assert ok
        assert v == 60

    def test_float_rounded_to_int(self):
        ok, _, v = parse_dwell_time("3.6")
        assert ok
        assert v == 4
        assert isinstance(v, int)

    def test_float_rounds_down(self):
        ok, _, v = parse_dwell_time("3.4")
        assert ok
        assert v == 3

    def test_result_is_int(self):
        _, _, v = parse_dwell_time("5")
        assert isinstance(v, int)

    def test_error_message_empty(self):
        ok, msg, _ = parse_dwell_time("")
        assert not ok
        assert "required" in msg.lower()


# ── parse_temperature ─────────────────────────────────────────────────────────

class TestParseTemperature:
    def test_empty_string(self):
        ok, _, _ = parse_temperature("", "Cool")
        assert not ok

    def test_non_numeric(self):
        ok, _, _ = parse_temperature("hot", "Cool")
        assert not ok

    def test_zero(self):
        ok, _, _ = parse_temperature("0", "Cool")
        assert not ok

    def test_negative(self):
        ok, _, _ = parse_temperature("-10", "Cool")
        assert not ok

    def test_above_max(self):
        ok, _, _ = parse_temperature("401", "Cool")
        assert not ok

    def test_valid_integer(self):
        ok, _, v = parse_temperature("200", "Cool")
        assert ok
        assert v == 200

    def test_valid_max(self):
        ok, _, v = parse_temperature("400", "Cool")
        assert ok
        assert v == 400

    def test_float_rounded_to_int(self):
        ok, _, v = parse_temperature("200.6", "Cool")
        assert ok
        assert v == 201
        assert isinstance(v, int)

    def test_result_is_int(self):
        _, _, v = parse_temperature("270", "Reheat")
        assert isinstance(v, int)

    def test_field_name_in_error_message(self):
        ok, msg, _ = parse_temperature("", "Reheat temperature")
        assert not ok
        assert "Reheat temperature" in msg

    def test_field_name_in_range_error(self):
        ok, msg, _ = parse_temperature("500", "Cool temperature")
        assert not ok
        assert "Cool temperature" in msg
