# Bambu G-Code Modifier

A Windows 11 desktop application for modifying G-Code exported from **Bambu Studio** to reduce oozing and stringing during multi-material toolchange travel.

# WARNING - THIS APP HAS NOT UNDERGONE QUALITY CONTROL AND GENERATED G-CODE SHOULD BE REVIEWED MANUALLY BEFORE USE TO VERIFY CORRECTNESS.

---

## The Problem

When a multi-material print on the H2D finishes a toolchange at the wipe tower (Foaming material in left nozzle, standard material in right nozzle), the nozzle immediately retracts and travels back to the part. Any molten filament still on the nozzle tip hangs in mid-air and gets dragged across the print surface, leaving stringing and blobs.

## The Solution

This app post-processes your Bambu Studio `.gcode` file to insert three actions **for the left nozzle** at each toolchange:

1. **Dwell** — hold position at the wipe tower for 3 seconds so gravity pulls any ooze down onto the tower rather than mid-air
2. **Wipe pass** — move the nozzle 5 mm across the tower surface to wipe off residual filament
3. **Retraction** — retract with your chosen distance before travelling to the print area

Optionally, the nozzle can also be **cooled before travel** and **reheated on arrival** to further reduce stringing.

---

## Features

- **Retraction distance control** — replace all retraction values in the file with a custom value (supports any Bambu file regardless of original retraction length)
- **Dwell + wipe insertion** — automatically inserted at every toolchange (`; CP TOOLCHANGE END`) in the file
- **Temperature before travel** — optionally cool the left nozzle (T1) to a set temperature before travelling, then reheat to printing temperature on arrival
- **Time comparison** — shows original print time, estimated edited time, and additional time added
- **Safe filename handling** — saves the edited file as `<name>_edited.gcode`; increments to `_edited_1`, `_edited_2`, etc. if a file already exists
- **Re-edit support** — loading a previously edited file correctly detects existing dwell blocks and shows accurate time estimates without inserting duplicate dwells

---

## Requirements

- Windows 10 / 11
- Python 3.10 or later
- [customtkinter](https://github.com/TomSchimansky/CustomTkinter)

Install dependencies:

```
pip install customtkinter pyinstaller
```

---

## Running from Source

```
cd gcode_editor
python main.py
```

## Building the Executable

Run `build.bat` from inside the `gcode_editor` folder:

```
build.bat
```

The standalone executable will be created at `gcode_editor\dist\GCodeEditor.exe`. No Python installation is required to run the `.exe`.

---

## Usage

1. Click **Select .gcode File...** and choose a Bambu Studio G-Code file
2. Enter a **Retraction Distance** in mm (the app will replace all existing retraction values with this value)
   - The field turns red if the value exceeds 14 mm as a caution
3. *(Optional)* Tick **Decrease Temperature Before Travel** and set:
   - **Cool to** — temperature to drop the left nozzle to before travel (e.g. 200 °C)
   - **Reheat to** — temperature to wait for on arrival at the print area (e.g. 270 °C)
   - > ⚠ Temperature changes apply to the **left nozzle (T1) only**. The right nozzle (T0) is not modified.
4. Click **Analyse File** to preview the changes and see the estimated additional print time
5. Click **Generate G-Code** to save the modified file

---

## G-Code Changes Made

### Retraction / de-retraction values

All occurrences of `G1 E-X F1800` and `G1 EX F1800` (standalone E-only moves at retraction speed) are replaced with the user-specified value. This keeps retract/de-retract pairs balanced throughout the file.

### Dwell + wipe block

Inserted before the retraction that follows each `; CP TOOLCHANGE END` marker:

```gcode
G4 S3          ; dwell 3 seconds - ooze falls on tower
G91            ; relative positioning for wipe
G1 X5 F3000    ; wipe pass over tower
G1 X-5 F3000   ; wipe back
G90            ; absolute positioning
```

### Temperature changes *(optional)*

Inserted immediately after the wipe block:

```gcode
M104 T1 S200   ; decrease LEFT nozzle (T1) to 200C before travel
```

Inserted before the de-retraction when the nozzle arrives at the print area:

```gcode
M109 T1 S270   ; wait for LEFT nozzle (T1) to reach 270C
```

---

## Compatibility

Tested against Bambu Studio G-Code for the **Bambu Lab H2D** printer. The retraction detection uses a generic pattern (`G1 E±value F1800`) so it works regardless of the retraction values configured in your slicer profile.

---

## License

See [LICENSE](LICENSE).
