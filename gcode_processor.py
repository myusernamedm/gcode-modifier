import re
import os
from dataclasses import dataclass

RETRACT_PATTERN   = re.compile(r'^G1 E-([\d.]+) F1800\s*$')
DERETRACT_PATTERN = re.compile(r'^G1 E([\d.]+) F1800\s*$')
TIME_PATTERN      = re.compile(
    r'total estimated time: (?:(\d+)d )?(\d+)h (\d+)m (\d+)s'
)
TOOLCHANGE_END = '; CP TOOLCHANGE END'
SEPARATOR      = ';------------------'
WIPE_END       = '; WIPE_END'


@dataclass
class ProcessingResult:
    lines: list
    original_seconds: int
    added_seconds: int
    insertions_made: int
    output_path: str


def parse_original_time(lines):
    """Parse total estimated print time from G-Code header. Returns seconds."""
    for line in lines[:20]:
        m = TIME_PATTERN.search(line)
        if m:
            days  = int(m.group(1)) if m.group(1) else 0
            hours = int(m.group(2))
            mins  = int(m.group(3))
            secs  = int(m.group(4))
            return days * 86400 + hours * 3600 + mins * 60 + secs
    raise ValueError(
        "Could not find 'total estimated time' in file header.\n"
        "Is this a Bambu Studio G-Code file?"
    )


def format_seconds(total):
    """Convert integer seconds to human-readable string like '20h 33m 30s'."""
    total = int(total)
    days  = total // 86400
    rem   = total % 86400
    hours = rem // 3600
    rem   = rem % 3600
    mins  = rem // 60
    secs  = rem % 60
    if days > 0:
        return f"{days}d {hours}h {mins}m {secs}s"
    return f"{hours}h {mins}m {secs}s"


def compute_output_path(input_path):
    """Inserts '_edited' before the .gcode extension."""
    root, ext = os.path.splitext(input_path)
    return root + '_edited' + ext


def find_unique_output_path(input_path):
    """
    Returns a unique output path that does not already exist.
    Starts with <name>_edited.gcode, then <name>_edited_1.gcode, etc.
    """
    root, ext = os.path.splitext(input_path)
    base = root + '_edited'
    candidate = base + ext
    if not os.path.exists(candidate):
        return candidate
    counter = 1
    while True:
        candidate = f"{base}_{counter}{ext}"
        if not os.path.exists(candidate):
            return candidate
        counter += 1


def process_lines(lines, retraction_value, add_temperature,
                  cool_temp=200, reheat_temp=270,
                  wipe_distance=5.0, dwell_time=3,
                  input_path='', progress_callback=None):
    """
    Single-pass state machine that:
      1. Replaces all G1 E-X F1800 retraction values with retraction_value
      2. Replaces all G1 EX F1800 de-retraction values with retraction_value,
         except after a '; WIPE_END' top-up retract where the de-retract is
         adjusted to retraction_value + (original_deretract - original_topup)
         to compensate for filament already retracted during the wipe moves
      3. After each '; CP TOOLCHANGE END' block (when a retraction follows),
         inserts: G4 S3 dwell + wipe pass of wipe_distance mm
         (+ optional M104 S{cool_temp})
      4. If add_temperature: also inserts M109 S{reheat_temp} before the
         de-retract at the part
      5. Detects existing dwell blocks (already-edited files) and counts them
         for accurate time display without inserting a duplicate dwell
    """
    value_str = f"{retraction_value:.1f}"
    retract_line   = f"G1 E-{value_str} F1800\n"
    deretract_line = f"G1 E{value_str} F1800\n"

    wipe_dist_str = f"{wipe_distance:.1f}"
    dwell_wipe_block = [
        f"G4 S{dwell_time} ; dwell {dwell_time} seconds - ooze falls on tower\n",
        "G91 ; relative positioning for wipe\n",
        f"G1 X{wipe_dist_str} F3000 ; wipe pass over tower\n",
        f"G1 X-{wipe_dist_str} F3000 ; wipe back\n",
        "G90 ; absolute positioning\n",
    ]

    output_lines  = []
    after_tc_end  = False
    saw_separator = False
    pending_temp  = False
    after_wipe_end = False
    wipe_topup     = None  # original top-up E- value seen after WIPE_END
    insertions    = 0
    total         = len(lines)

    for i, line in enumerate(lines):
        if progress_callback and i % 50000 == 0:
            progress_callback(int(i / total * 100))

        stripped = line.rstrip('\n').rstrip('\r').strip()

        # --- STATE: WIPE_END tracking (de-retract imbalance fix) ---
        if stripped == WIPE_END:
            after_wipe_end = True
            output_lines.append(line)
            continue

        if after_wipe_end:
            if stripped == '' or stripped.startswith(';'):
                output_lines.append(line)
                continue
            after_wipe_end = False
            m = RETRACT_PATTERN.match(stripped)
            if m:
                wipe_topup = float(m.group(1))
                output_lines.append(retract_line)
                continue
            # Not a retract after WIPE_END — fall through to normal processing

        # --- STATE: entering after-toolchange-end zone ---
        if stripped == TOOLCHANGE_END:
            after_tc_end  = True
            saw_separator = False
            output_lines.append(line)
            continue

        if after_tc_end and not saw_separator:
            if stripped == SEPARATOR:
                saw_separator = True
            output_lines.append(line)
            continue

        # --- STATE: inside after-toolchange-end zone, looking for first real line ---
        if after_tc_end and saw_separator:
            if stripped == '' or stripped.startswith(';'):
                output_lines.append(line)
                continue

            # First non-blank, non-comment line after CP TOOLCHANGE END
            if RETRACT_PATTERN.match(stripped):
                # Fresh file: insert new dwell + wipe before the retraction
                output_lines.extend(dwell_wipe_block)
                if add_temperature:
                    # T1 = left nozzle only; right nozzle (T0) is intentionally not modified
                    output_lines.append(
                        f"M104 T1 S{cool_temp} ; decrease LEFT nozzle (T1) to {cool_temp}C before travel\n"
                    )
                    pending_temp = True
                insertions += 1
            elif stripped.startswith('G4 S'):
                # Already-edited file: dwell block is already present — count it
                # for accurate time display but do not insert a second dwell
                insertions += 1

            # Reset state — consumed the TC-end zone
            after_tc_end  = False
            saw_separator = False
            # Fall through to normal processing below

        # --- TEMPERATURE M109 insertion: before de-retract at the part ---
        if pending_temp and DERETRACT_PATTERN.match(stripped):
            # T1 = left nozzle only; right nozzle (T0) is intentionally not modified
            output_lines.append(
                f"M109 T1 S{reheat_temp} ; wait for LEFT nozzle (T1) to reach {reheat_temp}C\n"
            )
            pending_temp = False
            # Fall through to emit the de-retract line itself

        # --- GLOBAL RETRACT / DE-RETRACT VALUE REPLACEMENT ---
        if RETRACT_PATTERN.match(stripped):
            output_lines.append(retract_line)
        elif wipe_topup is not None and DERETRACT_PATTERN.match(stripped):
            # De-retract after a wipe-during-retract sequence: the wipe moves
            # already retracted (original_deretract - topup) mm, so we must
            # de-retract that extra amount on top of the user's retraction value.
            m = DERETRACT_PATTERN.match(stripped)
            deretract_original = float(m.group(1))
            wipe_retracted = deretract_original - wipe_topup
            adjusted = retraction_value + wipe_retracted
            output_lines.append(f"G1 E{adjusted:.2f} F1800\n")
            wipe_topup = None
        elif DERETRACT_PATTERN.match(stripped):
            output_lines.append(deretract_line)
        else:
            output_lines.append(line)

    if progress_callback:
        progress_callback(100)

    original_seconds = parse_original_time(lines)
    added_seconds    = insertions * dwell_time
    if add_temperature:
        added_seconds += insertions * 90

    return ProcessingResult(
        lines            = output_lines,
        original_seconds = original_seconds,
        added_seconds    = added_seconds,
        insertions_made  = insertions,
        output_path      = compute_output_path(input_path),
    )


def write_output(lines, output_path):
    """Write processed lines to output_path."""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        f.writelines(lines)
