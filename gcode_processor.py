import re
import os
from dataclasses import dataclass

RETRACT_PATTERN   = re.compile(r'^G1 E-([\d.]+) F1800\s*$')
DERETRACT_PATTERN = re.compile(r'^G1 E([\d.]+) F1800\s*$')
TIME_PATTERN      = re.compile(
    r'total estimated time: (?:(\d+)d )?(\d+)h (\d+)m (\d+)s'
)
TOOLCHANGE_START        = '; CP TOOLCHANGE START'
TOOLCHANGE_END          = '; CP TOOLCHANGE END'
SEPARATOR               = ';------------------'
WIPE_END                = '; WIPE_END'
MACHINE_START_GCODE_END = '; MACHINE_START_GCODE_END'


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
      1. Passes the machine start section (before MACHINE_START_GCODE_END)
         through completely unchanged — startup priming retractions are untouched.
      2. After each '; CP TOOLCHANGE END' block, if a retraction follows, inserts:
         G4 S{dwell_time} dwell + relative wipe pass of wipe_distance mm.
      3. Replaces ONLY the toolchange retraction (the one right after CP TOOLCHANGE
         END + separator) and its matching de-retraction at the part.
         All other retractions (layer changes, normal moves) are left untouched.
      4. If add_temperature: inserts M104 T1 S{cool_temp} after the wipe and
         M109 T1 S{reheat_temp} before the de-retract at the part.
      5. Detects existing dwell blocks (already-edited files) and updates their
         retraction value without inserting a duplicate dwell.
      6. WIPE_END top-up adjustment: if a wipe-during-retract occurs during
         toolchange travel, the de-retract is adjusted to compensate.
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

    output_lines        = []
    before_print        = True   # True until MACHINE_START_GCODE_END
    in_toolchange_block = False
    after_tc_end        = False
    saw_separator       = False
    pending_temp        = False
    tc_await_retract    = False  # already-edited file: scanning wipe block for retraction
    tc_retract_active   = False  # TC retraction replaced; awaiting matching de-retract
    after_wipe_end      = False
    wipe_topup          = None   # original top-up E- value seen after WIPE_END
    insertions          = 0
    total               = len(lines)

    for i, line in enumerate(lines):
        if progress_callback and i % 50000 == 0:
            progress_callback(int(i / total * 100))

        stripped = line.rstrip('\n').rstrip('\r').strip()

        # ----------------------------------------------------------------
        # Machine start section: pass through completely unchanged
        # ----------------------------------------------------------------
        if before_print:
            output_lines.append(line)
            if stripped == MACHINE_START_GCODE_END:
                before_print = False
            continue

        # ----------------------------------------------------------------
        # CP TOOLCHANGE block boundaries
        # ----------------------------------------------------------------
        if stripped == TOOLCHANGE_START:
            in_toolchange_block = True
            after_wipe_end = False
            wipe_topup = None
            output_lines.append(line)
            continue

        if stripped == TOOLCHANGE_END:
            in_toolchange_block = False
            after_tc_end  = True
            saw_separator = False
            output_lines.append(line)
            continue

        # Inside toolchange block: pass through unchanged
        if in_toolchange_block:
            output_lines.append(line)
            continue

        # ----------------------------------------------------------------
        # WIPE_END top-up tracking — only while awaiting TC de-retract
        # ----------------------------------------------------------------
        if tc_retract_active and stripped == WIPE_END:
            after_wipe_end = True
            output_lines.append(line)
            continue

        if tc_retract_active and after_wipe_end:
            if stripped == '' or stripped.startswith(';'):
                output_lines.append(line)
                continue
            after_wipe_end = False
            m = RETRACT_PATTERN.match(stripped)
            if m:
                wipe_topup = float(m.group(1))
                output_lines.append(retract_line)
                continue
            # Not a retract after WIPE_END — fall through to normal handling

        # ----------------------------------------------------------------
        # Wait for ;------------------ separator after CP TOOLCHANGE END
        # ----------------------------------------------------------------
        if after_tc_end and not saw_separator:
            if stripped == SEPARATOR:
                saw_separator = True
            output_lines.append(line)
            continue

        # ----------------------------------------------------------------
        # First non-blank/non-comment line after CP TOOLCHANGE END
        # ----------------------------------------------------------------
        if after_tc_end and saw_separator:
            if stripped == '' or stripped.startswith(';'):
                output_lines.append(line)
                continue

            after_tc_end  = False
            saw_separator = False

            if RETRACT_PATTERN.match(stripped):
                # Fresh file: insert dwell + wipe, replace the retraction
                output_lines.extend(dwell_wipe_block)
                if add_temperature:
                    output_lines.append(
                        f"M104 T1 S{cool_temp} ; decrease LEFT nozzle (T1) to {cool_temp}C before travel\n"
                    )
                    pending_temp = True
                output_lines.append(retract_line)
                tc_retract_active = True
                insertions += 1
            elif stripped.startswith('G4 S'):
                # Already-edited file: dwell exists — count it, scan ahead for retraction
                insertions += 1
                tc_await_retract = True
                output_lines.append(line)
            else:
                output_lines.append(line)
            continue

        # ----------------------------------------------------------------
        # Already-edited: scan wipe block lines until the retraction
        # ----------------------------------------------------------------
        if tc_await_retract:
            if RETRACT_PATTERN.match(stripped):
                output_lines.append(retract_line)
                tc_await_retract  = False
                tc_retract_active = True
            else:
                output_lines.append(line)
            continue

        # ----------------------------------------------------------------
        # M109 insertion before the TC de-retract at the part
        # ----------------------------------------------------------------
        if pending_temp and tc_retract_active and DERETRACT_PATTERN.match(stripped):
            output_lines.append(
                f"M109 T1 S{reheat_temp} ; wait for LEFT nozzle (T1) to reach {reheat_temp}C\n"
            )
            pending_temp = False
            # fall through to replace the de-retract below

        # ----------------------------------------------------------------
        # Replace the TC de-retract (only when awaiting it)
        # ----------------------------------------------------------------
        if tc_retract_active and DERETRACT_PATTERN.match(stripped):
            if wipe_topup is not None:
                m = DERETRACT_PATTERN.match(stripped)
                deretract_original = float(m.group(1))
                wipe_retracted = deretract_original - wipe_topup
                adjusted = retraction_value + wipe_retracted
                output_lines.append(f"G1 E{adjusted:.2f} F1800\n")
                wipe_topup = None
            else:
                output_lines.append(deretract_line)
            tc_retract_active = False
            continue

        # ----------------------------------------------------------------
        # All other lines: pass through unchanged
        # ----------------------------------------------------------------
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
