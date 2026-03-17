"""
Unit tests for gcode_processor.py
Run with: pytest test_gcode_processor.py -v
"""
import pytest
from unittest.mock import patch

from gcode_processor import (
    parse_original_time,
    format_seconds,
    compute_output_path,
    find_unique_output_path,
    process_lines,
    ProcessingResult,
)


# ── shared helpers ────────────────────────────────────────────────────────────

HEADER_SIMPLE = "; total estimated time: 20h 33m 30s\n"
HEADER_DAYS   = "; total estimated time: 1d 14h 12m 0s\n"


def make_lines(*body_lines, header=HEADER_SIMPLE):
    """Wrap body lines in a minimal header so parse_original_time succeeds."""
    return [header] + list(body_lines)


def tc_block(first_line="G1 E-3.5 F1800\n"):
    """Minimal toolchange-end block followed by first_line."""
    return [
        "; CP TOOLCHANGE END\n",
        ";------------------\n",
        "\n",
        first_line,
    ]


def run(lines, retraction=3.5, temp=False, cool=200, reheat=270,
        wipe=5.0, dwell=3):
    return process_lines(
        lines, retraction, temp,
        cool_temp=cool, reheat_temp=reheat,
        wipe_distance=wipe, dwell_time=dwell,
        input_path="test.gcode",
    )


# ── parse_original_time ───────────────────────────────────────────────────────

class TestParseOriginalTime:
    def test_hours_minutes_seconds(self):
        lines = [HEADER_SIMPLE]
        assert parse_original_time(lines) == 20 * 3600 + 33 * 60 + 30

    def test_days_format(self):
        lines = [HEADER_DAYS]
        assert parse_original_time(lines) == 86400 + 14 * 3600 + 12 * 60

    def test_found_at_line_19(self):
        padding = ["; some comment\n"] * 19
        lines = padding + [HEADER_SIMPLE]
        assert parse_original_time(lines) == 20 * 3600 + 33 * 60 + 30

    def test_not_found_after_line_20_raises(self):
        padding = ["; some comment\n"] * 20
        lines = padding + [HEADER_SIMPLE]
        with pytest.raises(ValueError):
            parse_original_time(lines)

    def test_missing_raises(self):
        with pytest.raises(ValueError):
            parse_original_time(["; no time here\n"])

    def test_zero_time(self):
        lines = ["; total estimated time: 0h 0m 0s\n"]
        assert parse_original_time(lines) == 0

    def test_large_days(self):
        lines = ["; total estimated time: 2d 3h 4m 5s\n"]
        assert parse_original_time(lines) == 2 * 86400 + 3 * 3600 + 4 * 60 + 5


# ── format_seconds ────────────────────────────────────────────────────────────

class TestFormatSeconds:
    def test_simple_hours(self):
        assert format_seconds(3600) == "1h 0m 0s"

    def test_hours_minutes_seconds(self):
        assert format_seconds(20 * 3600 + 33 * 60 + 30) == "20h 33m 30s"

    def test_with_days(self):
        assert format_seconds(86400 + 14 * 3600 + 12 * 60) == "1d 14h 12m 0s"

    def test_zero(self):
        assert format_seconds(0) == "0h 0m 0s"

    def test_float_input_truncated(self):
        assert format_seconds(3600.9) == "1h 0m 0s"

    def test_one_day_exactly(self):
        assert format_seconds(86400) == "1d 0h 0m 0s"

    def test_no_days_prefix_below_one_day(self):
        result = format_seconds(23 * 3600 + 59 * 60 + 59)
        assert result.startswith("23h")
        assert "d" not in result


# ── compute_output_path ───────────────────────────────────────────────────────

class TestComputeOutputPath:
    def test_adds_edited_suffix(self):
        assert compute_output_path("/some/path/file.gcode") == "/some/path/file_edited.gcode"

    def test_preserves_extension(self):
        assert compute_output_path("C:/folder/print.gcode").endswith("_edited.gcode")

    def test_name_without_extension(self):
        result = compute_output_path("file.gcode")
        assert result == "file_edited.gcode"


# ── find_unique_output_path ───────────────────────────────────────────────────

class TestFindUniqueOutputPath:
    def test_no_conflict_returns_edited(self):
        with patch("gcode_processor.os.path.exists", return_value=False):
            assert find_unique_output_path("/p/f.gcode") == "/p/f_edited.gcode"

    def test_conflict_returns_numbered(self):
        with patch("gcode_processor.os.path.exists", side_effect=[True, False]):
            assert find_unique_output_path("/p/f.gcode") == "/p/f_edited_1.gcode"

    def test_multiple_conflicts(self):
        with patch("gcode_processor.os.path.exists", side_effect=[True, True, True, False]):
            assert find_unique_output_path("/p/f.gcode") == "/p/f_edited_3.gcode"


# ── retraction / de-retraction replacement ───────────────────────────────────

class TestRetractionReplacement:
    def test_retract_replaced(self):
        result = run(make_lines("G1 E-14 F1800\n"), retraction=3.5)
        assert "G1 E-3.5 F1800\n" in result.lines
        assert "G1 E-14 F1800\n" not in result.lines

    def test_deretract_replaced(self):
        result = run(make_lines("G1 E14 F1800\n"), retraction=3.5)
        assert "G1 E3.5 F1800\n" in result.lines
        assert "G1 E14 F1800\n" not in result.lines

    def test_no_leading_zero_retract(self):
        result = run(make_lines("G1 E-.8 F1800\n"), retraction=3.5)
        assert "G1 E-3.5 F1800\n" in result.lines
        assert "G1 E-.8 F1800\n" not in result.lines

    def test_no_leading_zero_deretract(self):
        result = run(make_lines("G1 E.8 F1800\n"), retraction=3.5)
        assert "G1 E3.5 F1800\n" in result.lines

    def test_retraction_value_format(self):
        # integer input should be formatted with one decimal place
        result = run(make_lines("G1 E-5 F1800\n"), retraction=4.0)
        assert "G1 E-4.0 F1800\n" in result.lines

    def test_non_retract_line_unchanged(self):
        result = run(make_lines("G1 X100 Y200 F3000\n"))
        assert "G1 X100 Y200 F3000\n" in result.lines

    def test_different_feedrate_not_replaced(self):
        result = run(make_lines("G1 E-3.5 F600\n"), retraction=5.0)
        assert "G1 E-3.5 F600\n" in result.lines
        assert "G1 E-5.0 F600\n" not in result.lines

    def test_comment_not_replaced(self):
        result = run(make_lines("; G1 E-3.5 F1800\n"))
        assert "; G1 E-3.5 F1800\n" in result.lines

    def test_multiple_retracts_all_replaced(self):
        lines = make_lines(
            "G1 E-14 F1800\n",
            "G1 X100 F3000\n",
            "G1 E-14 F1800\n",
        )
        result = run(lines, retraction=3.5)
        assert result.lines.count("G1 E-3.5 F1800\n") == 2


# ── toolchange dwell / wipe insertion ────────────────────────────────────────

class TestToolchangeInsertion:
    def test_dwell_inserted_before_retract(self):
        lines = make_lines(*tc_block("G1 E-3.5 F1800\n"))
        result = run(lines)
        assert result.insertions_made == 1
        dwell_idx   = next(i for i, l in enumerate(result.lines) if l.startswith("G4 S"))
        retract_idx = next(i for i, l in enumerate(result.lines) if "G1 E-3.5 F1800" in l)
        assert dwell_idx < retract_idx

    def test_dwell_uses_configured_time(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")), dwell=7)
        assert any("G4 S7" in l for l in result.lines)

    def test_wipe_uses_configured_distance(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")), wipe=12.0)
        assert any("G1 X12.0" in l for l in result.lines)
        assert any("G1 X-12.0" in l for l in result.lines)

    def test_wipe_block_contains_relative_positioning(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")))
        assert any("G91" in l for l in result.lines)
        assert any("G90" in l for l in result.lines)

    def test_no_insertion_when_move_follows(self):
        lines = make_lines(*tc_block("G1 X100 Y100 F3000\n"))
        result = run(lines)
        assert result.insertions_made == 0
        assert not any("G4 S" in l for l in result.lines)

    def test_already_edited_not_doubled(self):
        lines = make_lines(
            "; CP TOOLCHANGE END\n",
            ";------------------\n",
            "\n",
            "G4 S3 ; dwell 3 seconds - ooze falls on tower\n",
            "G91 ; relative positioning for wipe\n",
            "G1 X5.0 F3000 ; wipe pass over tower\n",
            "G1 X-5.0 F3000 ; wipe back\n",
            "G90 ; absolute positioning\n",
            "G1 E-3.5 F1800\n",
        )
        result = run(lines)
        assert result.insertions_made == 1
        assert sum(1 for l in result.lines if l.startswith("G4 S")) == 1

    def test_already_edited_any_dwell_time_detected(self):
        # The already-edited detection must work regardless of original dwell time
        lines = make_lines(
            "; CP TOOLCHANGE END\n",
            ";------------------\n",
            "\n",
            "G4 S7 ; dwell 7 seconds - ooze falls on tower\n",
            "G1 E-3.5 F1800\n",
        )
        result = run(lines)
        assert result.insertions_made == 1

    def test_multiple_toolchanges_counted(self):
        block = tc_block("G1 E-3.5 F1800\n")
        result = run(make_lines(*block, *block))
        assert result.insertions_made == 2

    def test_blanks_and_comments_skipped_before_retract(self):
        lines = make_lines(
            "; CP TOOLCHANGE END\n",
            ";------------------\n",
            "\n",
            "; some comment\n",
            "\n",
            "G1 E-3.5 F1800\n",
        )
        result = run(lines)
        assert result.insertions_made == 1

    def test_toolchange_end_and_separator_preserved_in_output(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")))
        assert any("; CP TOOLCHANGE END" in l for l in result.lines)
        assert any(";------------------" in l for l in result.lines)


# ── temperature insertion ─────────────────────────────────────────────────────

class TestTemperatureInsertion:
    def test_m104_inserted_after_dwell(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")), temp=True, cool=180)
        assert any("M104 T1 S180" in l for l in result.lines)

    def test_m104_uses_cool_temp(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")), temp=True, cool=195)
        assert any("M104 T1 S195" in l for l in result.lines)
        assert not any("M104 T1 S200" in l for l in result.lines)

    def test_m109_inserted_before_deretract(self):
        lines = make_lines(
            *tc_block("G1 E-3.5 F1800\n"),
            "G1 X100 Y100 F3000\n",
            "G1 E3.5 F1800\n",
        )
        result = run(lines, temp=True, reheat=265)
        out = result.lines
        m109_idx      = next(i for i, l in enumerate(out) if "M109 T1 S265" in l)
        deretract_idx = next(i for i, l in enumerate(out) if l.strip() == "G1 E3.5 F1800")
        assert m109_idx < deretract_idx

    def test_no_temperature_when_disabled(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")), temp=False)
        assert not any("M104" in l for l in result.lines)
        assert not any("M109" in l for l in result.lines)

    def test_temperature_targets_t1_only(self):
        lines = make_lines(*tc_block("G1 E-3.5 F1800\n"), "G1 E3.5 F1800\n")
        result = run(lines, temp=True)
        for l in result.lines:
            if "M104" in l or "M109" in l:
                assert "T1" in l
                assert "T0" not in l

    def test_m109_uses_reheat_temp(self):
        lines = make_lines(*tc_block("G1 E-3.5 F1800\n"), "G1 E3.5 F1800\n")
        result = run(lines, temp=True, reheat=260)
        assert any("M109 T1 S260" in l for l in result.lines)


# ── wipe-end de-retract imbalance fix ────────────────────────────────────────

class TestWipeEndBalance:
    def _wipe_sequence(self, topup="G1 E-.04 F1800\n", deretract="G1 E.8 F1800\n"):
        return make_lines(
            "; WIPE_START\n",
            "G1 X100 Y100 E-.11\n",
            "G1 X101 Y100 E-.69\n",
            "; WIPE_END\n",
            topup,
            "G1 X200 Y200 F3000\n",
            deretract,
        )

    def test_adjusted_deretract_accounts_for_wipe(self):
        # topup=0.04, deretract_orig=0.8 → wipe_retracted=0.76
        # adjusted = user(3.5) + 0.76 = 4.26
        result = run(self._wipe_sequence(), retraction=3.5)
        assert "G1 E4.26 F1800\n" in result.lines

    def test_topup_replaced_with_user_value(self):
        result = run(self._wipe_sequence(), retraction=3.5)
        assert "G1 E-3.5 F1800\n" in result.lines
        assert "G1 E-.04 F1800\n" not in result.lines

    def test_wipe_moves_not_replaced(self):
        result = run(self._wipe_sequence(), retraction=3.5)
        assert "G1 X100 Y100 E-.11\n" in result.lines
        assert "G1 X101 Y100 E-.69\n" in result.lines

    def test_wipe_end_line_preserved(self):
        result = run(self._wipe_sequence(), retraction=3.5)
        assert "; WIPE_END\n" in result.lines

    def test_standalone_deretract_uses_plain_user_value(self):
        result = run(make_lines("G1 E14 F1800\n"), retraction=3.5)
        assert "G1 E3.5 F1800\n" in result.lines
        assert not any("E4.26" in l for l in result.lines)

    def test_no_retract_after_wipe_end_falls_through(self):
        # WIPE_END followed immediately by a move (not retract)
        # The subsequent de-retract should NOT be adjusted
        lines = make_lines(
            "; WIPE_END\n",
            "G1 X200 Y200 F3000\n",
            "G1 E.8 F1800\n",
        )
        result = run(lines, retraction=3.5)
        assert "G1 E3.5 F1800\n" in result.lines
        assert not any("E4.26" in l for l in result.lines)

    def test_different_topup_value(self):
        # topup=0.1, deretract_orig=0.8 → wipe_retracted=0.7
        # adjusted = 3.5 + 0.7 = 4.2
        lines = self._wipe_sequence(topup="G1 E-.1 F1800\n", deretract="G1 E.8 F1800\n")
        result = run(lines, retraction=3.5)
        assert "G1 E4.20 F1800\n" in result.lines

    def test_wipe_move_not_confused_with_retract(self):
        # "G1 X100 Y100 E-.11" has a different format — must NOT be matched by RETRACT_PATTERN
        result = run(self._wipe_sequence(), retraction=3.5)
        # wipe moves stay untouched
        assert "G1 X100 Y100 E-.11\n" in result.lines


# ── time accounting ───────────────────────────────────────────────────────────

class TestTimeAccounting:
    def test_added_seconds_dwell_times_insertions(self):
        block = tc_block("G1 E-3.5 F1800\n")
        result = run(make_lines(*block, *block), dwell=5)
        assert result.insertions_made == 2
        assert result.added_seconds == 10

    def test_temperature_adds_90s_per_insertion(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")), temp=True, dwell=3)
        assert result.added_seconds == 3 + 90

    def test_no_temp_no_extra_90s(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")), temp=False, dwell=3)
        assert result.added_seconds == 3

    def test_original_seconds_parsed_from_header(self):
        result = run(make_lines())
        assert result.original_seconds == 20 * 3600 + 33 * 60 + 30

    def test_original_seconds_days_format(self):
        result = run(make_lines(header=HEADER_DAYS))
        assert result.original_seconds == 86400 + 14 * 3600 + 12 * 60

    def test_zero_insertions_zero_added_seconds(self):
        result = run(make_lines("G1 X100 F3000\n"))
        assert result.insertions_made == 0
        assert result.added_seconds == 0


# ── progress callback ─────────────────────────────────────────────────────────

class TestProgressCallback:
    def test_callback_called_with_100_at_end(self):
        calls = []
        process_lines(make_lines("G1 X100\n"), 3.5, False,
                      progress_callback=calls.append)
        assert calls[-1] == 100

    def test_callback_values_non_decreasing(self):
        calls = []
        lines = make_lines(*["G1 X100\n"] * 200000)
        process_lines(lines, 3.5, False, progress_callback=calls.append)
        for a, b in zip(calls, calls[1:]):
            assert a <= b

    def test_no_callback_does_not_raise(self):
        process_lines(make_lines("G1 X100\n"), 3.5, False)


# ── output path helpers ───────────────────────────────────────────────────────

class TestOutputPath:
    def test_result_output_path_computed(self):
        result = run(make_lines(), retraction=3.5)
        assert result.output_path == "test_edited.gcode"

    def test_insertions_made_in_result(self):
        result = run(make_lines(*tc_block("G1 E-3.5 F1800\n")))
        assert result.insertions_made == 1
