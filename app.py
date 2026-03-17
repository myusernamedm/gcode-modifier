import os
import threading
from tkinter import filedialog

import customtkinter as ctk

from gcode_processor import (
    process_lines, write_output,
    format_seconds, find_unique_output_path,
)
from validators import (
    parse_retraction, parse_wipe_distance,
    parse_dwell_time, parse_temperature,
)
import theme as T

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class GCodeEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Bambu G-Code Editor")
        self.geometry("700x800")
        self.resizable(False, False)
        self.configure(fg_color=T.BG_MAIN)

        self.input_path = None
        self.result = None

        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self._build_header()
        self._build_file_panel()
        self._sep()
        self._build_settings_panel()
        self._sep()
        self._build_temperature_panel()
        self._sep()
        self._build_buttons()
        self._build_progress()
        self._sep()
        self._build_time_panel()
        self._sep()
        self._build_status()

    def _sep(self):
        ctk.CTkFrame(self, height=1, fg_color=T.SEPARATOR_CLR,
                     corner_radius=0).pack(fill="x", padx=0, pady=0)

    def _lbl(self, parent, text, color=None, size=None, weight="normal", width=0, anchor="w"):
        kw = dict(
            text=text,
            text_color=color or T.TEXT_LABEL,
            font=ctk.CTkFont(T.FONT_FAMILY, size or T.FS_BODY, weight=weight),
            anchor=anchor,
        )
        if width:
            kw["width"] = width
        return ctk.CTkLabel(parent, **kw)

    def _entry(self, parent, width=100, placeholder=""):
        return ctk.CTkEntry(
            parent,
            width=width,
            placeholder_text=placeholder,
            fg_color=T.BG_ENTRY,
            border_color=T.BORDER,
            border_width=1,
            text_color=T.TEXT_VALUE,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_BODY),
        )

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=T.BG_PANEL, corner_radius=0)
        hdr.pack(fill="x")
        inner = ctk.CTkFrame(hdr, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=14)
        self._lbl(inner, "BAMBU G-CODE EDITOR",
                  color=T.NEON_GREEN, size=T.FS_TITLE, weight="bold").pack(side="left")
        self._lbl(inner, "toolchange dwell · wipe · retraction",
                  color=T.TEXT_LABEL, size=T.FS_SMALL).pack(side="left", padx=(16, 0))

    def _build_file_panel(self):
        frame = ctk.CTkFrame(self, fg_color=T.BG_PANEL, corner_radius=0)
        frame.pack(fill="x")
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=12)

        self.pick_btn = ctk.CTkButton(
            row, text="Select .gcode File",
            width=160, height=32,
            fg_color=T.BTN_ANALYSE_BG, hover_color=T.BTN_ANALYSE_HOVER,
            text_color=T.NEON_BLUE,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_BODY, weight="bold"),
            border_width=1, border_color=T.NEON_BLUE,
            command=self._pick_file,
        )
        self.pick_btn.pack(side="left")

        self.file_label = ctk.CTkLabel(
            row, text="No file selected",
            anchor="w", wraplength=440,
            text_color=T.TEXT_LABEL,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_BODY),
        )
        self.file_label.pack(side="left", padx=(14, 0), fill="x", expand=True)

    def _build_settings_panel(self):
        panel = ctk.CTkFrame(self, fg_color=T.BG_PANEL, corner_radius=0)
        panel.pack(fill="x")

        self._lbl(panel, "SETTINGS", color=T.TEXT_LABEL,
                  size=T.FS_SMALL, weight="bold").pack(anchor="w", padx=20, pady=(12, 4))

        # Retraction distance
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=4)
        self._lbl(row, "Retraction Distance (mm)", width=T.LABEL_W).pack(side="left")
        self.retraction_entry = self._entry(row, placeholder="e.g. 3.5")
        self.retraction_entry.pack(side="left", padx=(10, 0))
        self.retraction_entry.bind("<KeyRelease>", self._on_retraction_changed)
        self.retraction_hint = self._lbl(row, "", color=T.TEXT_LABEL, width=220)
        self.retraction_hint.pack(side="left", padx=(10, 0))

        # Wipe distance
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=4)
        self._lbl(row, "Wipe Distance (mm)", width=T.LABEL_W).pack(side="left")
        self.wipe_dist_entry = self._entry(row, placeholder="e.g. 5")
        self.wipe_dist_entry.insert(0, "5")
        self.wipe_dist_entry.pack(side="left", padx=(10, 0))
        self._lbl(row, "mm — wipe pass length after toolchange dwell",
                  color=T.TEXT_LABEL, size=T.FS_SMALL).pack(side="left", padx=(10, 0))

        # Dwell time
        row = ctk.CTkFrame(panel, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(4, 12))
        self._lbl(row, "Dwell Time (s)", width=T.LABEL_W).pack(side="left")
        self.dwell_time_entry = self._entry(row, placeholder="e.g. 3")
        self.dwell_time_entry.insert(0, "3")
        self.dwell_time_entry.pack(side="left", padx=(10, 0))
        self._lbl(row, "s — pause at tower before travel",
                  color=T.TEXT_LABEL, size=T.FS_SMALL).pack(side="left", padx=(10, 0))

    def _build_temperature_panel(self):
        panel = ctk.CTkFrame(self, fg_color=T.BG_PANEL, corner_radius=0)
        panel.pack(fill="x")

        outer = ctk.CTkFrame(panel, fg_color="transparent")
        outer.pack(fill="x", padx=20, pady=12)

        self.temp_var = ctk.BooleanVar(value=False)
        self.temp_check = ctk.CTkCheckBox(
            outer,
            text="Decrease Temperature Before Travel",
            variable=self.temp_var,
            command=self._on_temp_toggled,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_BODY),
            text_color=T.TEXT_VALUE,
            fg_color=T.NEON_BLUE,
            hover_color=T.BTN_ANALYSE_HOVER,
            border_color=T.BORDER,
            checkmark_color=T.BG_MAIN,
        )
        self.temp_check.pack(anchor="w")

        # Sub-row: temperature entries
        self._temp_inputs = ctk.CTkFrame(outer, fg_color="transparent")
        self._temp_inputs.pack(fill="x", padx=(28, 0), pady=(8, 4))

        self._lbl(self._temp_inputs, "Cool to:").pack(side="left")
        self.cool_temp_entry = self._entry(self._temp_inputs, width=80, placeholder="200")
        self.cool_temp_entry.insert(0, "200")
        self.cool_temp_entry.configure(state="disabled")
        self.cool_temp_entry.pack(side="left", padx=(8, 2))
        self._lbl(self._temp_inputs, "°C").pack(side="left")

        self._lbl(self._temp_inputs, "     Reheat to:").pack(side="left")
        self.reheat_temp_entry = self._entry(self._temp_inputs, width=80, placeholder="270")
        self.reheat_temp_entry.insert(0, "270")
        self.reheat_temp_entry.configure(state="disabled")
        self.reheat_temp_entry.pack(side="left", padx=(8, 2))
        self._lbl(self._temp_inputs, "°C").pack(side="left")

        # Warning
        self.temp_warning = ctk.CTkLabel(
            outer,
            text="⚠  Temperature changes apply to the LEFT nozzle (T1) only."
                 "  Right nozzle (T0) is not modified.",
            text_color=T.NEON_ORANGE,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_SMALL),
            anchor="w",
        )
        self.temp_warning.pack(fill="x", padx=(28, 0), pady=(4, 0))
        self.temp_warning.pack_forget()

    def _build_buttons(self):
        frame = ctk.CTkFrame(self, fg_color=T.BG_MAIN, corner_radius=0)
        frame.pack(fill="x", padx=20, pady=14)

        self.edit_btn = ctk.CTkButton(
            frame, text="ANALYSE FILE",
            width=220, height=42,
            fg_color=T.BTN_ANALYSE_BG, hover_color=T.BTN_ANALYSE_HOVER,
            text_color=T.NEON_BLUE,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_BTN, weight="bold"),
            border_width=1, border_color=T.NEON_BLUE,
            corner_radius=4,
            command=self._on_edit_click,
        )
        self.edit_btn.pack(side="left")

        self.gen_btn = ctk.CTkButton(
            frame, text="GENERATE G-CODE",
            width=220, height=42,
            fg_color=T.BTN_GENERATE_BG, hover_color=T.BTN_GENERATE_HOVER,
            text_color=T.NEON_GREEN,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_BTN, weight="bold"),
            border_width=1, border_color=T.NEON_GREEN,
            corner_radius=4,
            command=self._on_generate_click,
        )
        self.gen_btn.pack(side="left", padx=(16, 0))

    def _build_progress(self):
        self._progress_frame = ctk.CTkFrame(self, fg_color=T.BG_MAIN, corner_radius=0)
        self._progress_frame.pack(fill="x", padx=20, pady=(0, 6))

        self.progress_bar = ctk.CTkProgressBar(
            self._progress_frame, width=520,
            fg_color=T.BG_PANEL,
            progress_color=T.NEON_BLUE,
        )
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(
            self._progress_frame, text="0%", width=40,
            text_color=T.NEON_BLUE,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_SMALL),
        )
        self._hide_progress()

    def _build_time_panel(self):
        panel = ctk.CTkFrame(self, fg_color=T.BG_PANEL, corner_radius=0)
        panel.pack(fill="x")

        self._lbl(panel, "PRINT TIME ESTIMATE", color=T.TEXT_LABEL,
                  size=T.FS_SMALL, weight="bold").pack(anchor="w", padx=20, pady=(12, 6))

        grid = ctk.CTkFrame(panel, fg_color="transparent")
        grid.pack(fill="x", padx=20, pady=(0, 12))

        headers = ["Original Time", "Edited Time", "Additional Time"]
        self.time_value_labels = []

        for col, header in enumerate(headers):
            col_frame = ctk.CTkFrame(grid, fg_color=T.BG_MAIN,
                                     corner_radius=4, border_width=1,
                                     border_color=T.BORDER)
            col_frame.grid(row=0, column=col, padx=(0, 10) if col < 2 else (0, 0),
                           pady=0, sticky="nsew")
            grid.columnconfigure(col, weight=1)

            self._lbl(col_frame, header, color=T.TEXT_LABEL,
                      size=T.FS_SMALL, anchor="center").pack(pady=(8, 2), padx=12)

            val = ctk.CTkLabel(
                col_frame, text="--",
                text_color=T.TEXT_WHITE,
                font=ctk.CTkFont(T.FONT_FAMILY, T.FS_VALUE, weight="bold"),
                anchor="center",
            )
            val.pack(pady=(0, 10), padx=12)
            self.time_value_labels.append(val)

    def _build_status(self):
        frame = ctk.CTkFrame(self, fg_color=T.BG_MAIN, corner_radius=0)
        frame.pack(fill="x", padx=20, pady=10)
        self.status_label = ctk.CTkLabel(
            frame,
            text="Select a .gcode file and enter settings to begin.",
            wraplength=660, anchor="w",
            text_color=T.TEXT_LABEL,
            font=ctk.CTkFont(T.FONT_FAMILY, T.FS_BODY),
        )
        self.status_label.pack(fill="x")

    # ── file picker ───────────────────────────────────────────────────────────

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Select G-Code File",
            filetypes=[("G-Code files", "*.gcode"), ("All files", "*.*")],
        )
        if not path:
            return
        self.input_path = path
        self.result = None
        self.file_label.configure(text=os.path.basename(path), text_color=T.TEXT_VALUE)
        self._reset_time_display()
        self._set_status("File loaded. Enter settings and click Analyse File.", "dim")

    # ── temperature toggle ────────────────────────────────────────────────────

    def _on_temp_toggled(self):
        enabled = self.temp_var.get()
        state = "normal" if enabled else "disabled"
        self.cool_temp_entry.configure(state=state)
        self.reheat_temp_entry.configure(state=state)
        if enabled:
            self.temp_warning.pack(fill="x", padx=(28, 0), pady=(4, 0))
        else:
            self.temp_warning.pack_forget()

    # ── inline validation (retraction field) ─────────────────────────────────

    def _on_retraction_changed(self, _event=None):
        raw = self.retraction_entry.get().strip()
        valid, _, value = parse_retraction(raw)

        if not raw:
            self._set_field_error(self.retraction_entry, False)
            self.retraction_hint.configure(text="")
            return

        if not valid:
            self._set_field_error(self.retraction_entry, True)
            self.retraction_hint.configure(text="Invalid value", text_color=T.NEON_RED)
            return

        if value > 14:
            self._set_field_error(self.retraction_entry, True)
            self.retraction_hint.configure(
                text=f"⚠ {value}mm is a large retraction",
                text_color=T.NEON_ORANGE,
            )
        else:
            self._set_field_error(self.retraction_entry, False)
            self.retraction_hint.configure(text="")

    # ── field error helper ────────────────────────────────────────────────────

    def _set_field_error(self, entry, has_error):
        entry.configure(fg_color=T.FIELD_ERROR_CLR if has_error else T.FIELD_NORMAL_CLR)

    # ── input validation ──────────────────────────────────────────────────────

    def _validate_inputs(self):
        """
        Validates all fields, highlighting every invalid one in red.
        Returns (is_valid, error_msg, retraction, wipe_dist, dwell_time, cool, reheat).
        """
        if not self.input_path:
            return False, "Please select a .gcode file.", 0.0, 0.0, 0, 0, 0
        if not os.path.exists(self.input_path):
            return False, f"File not found: {self.input_path}", 0.0, 0.0, 0, 0, 0
        if not self.input_path.lower().endswith('.gcode'):
            return False, "Selected file must have a .gcode extension.", 0.0, 0.0, 0, 0, 0

        errors = []

        ok, msg, ret_val = parse_retraction(self.retraction_entry.get().strip())
        self._set_field_error(self.retraction_entry, not ok)
        if not ok:
            errors.append(f"Retraction distance: {msg}")

        ok, msg, wipe_val = parse_wipe_distance(self.wipe_dist_entry.get().strip())
        self._set_field_error(self.wipe_dist_entry, not ok)
        if not ok:
            errors.append(f"Wipe distance: {msg}")

        ok, msg, dwell_val = parse_dwell_time(self.dwell_time_entry.get().strip())
        self._set_field_error(self.dwell_time_entry, not ok)
        if not ok:
            errors.append(f"Dwell time: {msg}")

        cool_val, reheat_val = 200, 270
        if self.temp_var.get():
            ok, msg, cool_val = parse_temperature(
                self.cool_temp_entry.get().strip(), "Cool temperature"
            )
            self._set_field_error(self.cool_temp_entry, not ok)
            if not ok:
                errors.append(msg)

            ok, msg, reheat_val = parse_temperature(
                self.reheat_temp_entry.get().strip(), "Reheat temperature"
            )
            self._set_field_error(self.reheat_temp_entry, not ok)
            if not ok:
                errors.append(msg)

        if errors:
            return False, errors[0], 0.0, 0.0, 0, 0, 0

        return True, "", ret_val, wipe_val, dwell_val, cool_val, reheat_val

    # ── button handlers ───────────────────────────────────────────────────────

    def _on_edit_click(self):
        ok, msg, ret_val, wipe_val, dwell_val, cool, reheat = self._validate_inputs()
        if not ok:
            self._set_status(msg, "error")
            return
        self._set_buttons_state("disabled")
        self._show_progress()
        self._set_status("Analysing G-Code…", "dim")
        threading.Thread(
            target=self._run_processing,
            args=(ret_val, wipe_val, dwell_val, cool, reheat, False),
            daemon=True,
        ).start()

    def _on_generate_click(self):
        ok, msg, ret_val, wipe_val, dwell_val, cool, reheat = self._validate_inputs()
        if not ok:
            self._set_status(msg, "error")
            return
        self._set_buttons_state("disabled")
        self._show_progress()
        self._set_status("Processing and saving G-Code…", "dim")
        threading.Thread(
            target=self._run_processing,
            args=(ret_val, wipe_val, dwell_val, cool, reheat, True),
            daemon=True,
        ).start()

    # ── background processing ─────────────────────────────────────────────────

    def _run_processing(self, retraction_value, wipe_distance, dwell_time,
                        cool_temp, reheat_temp, save_to_disk):
        try:
            with open(self.input_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            result = process_lines(
                lines,
                retraction_value,
                self.temp_var.get(),
                cool_temp=cool_temp,
                reheat_temp=reheat_temp,
                wipe_distance=wipe_distance,
                dwell_time=dwell_time,
                input_path=self.input_path,
                progress_callback=self._update_progress,
            )

            if save_to_disk:
                save_path = find_unique_output_path(self.input_path)
                write_output(result.lines, save_path)
                result.output_path = save_path

            self.after(0, self._on_processing_done, result, save_to_disk)
        except Exception as e:
            self.after(0, self._on_processing_error, str(e))

    def _update_progress(self, percent):
        self.after(0, lambda p=percent: self.progress_bar.set(p / 100))
        self.after(0, lambda p=percent: self.progress_label.configure(text=f"{p}%"))

    def _on_processing_done(self, result, saved):
        self.result = result
        self._hide_progress()
        self._set_buttons_state("normal")

        orig_str = format_seconds(result.original_seconds)
        new_str  = format_seconds(result.original_seconds + result.added_seconds)
        add_str  = f"+{format_seconds(result.added_seconds)}"

        self.time_value_labels[0].configure(text=orig_str, text_color=T.TEXT_WHITE)
        self.time_value_labels[1].configure(text=new_str,  text_color=T.TEXT_WHITE)
        self.time_value_labels[2].configure(text=add_str,  text_color=T.NEON_ORANGE)

        if saved:
            fname = os.path.basename(result.output_path)
            self._set_status(
                f"Saved: {fname}  ({result.insertions_made} toolchange locations modified)",
                "success",
            )
        else:
            self._set_status(
                f"Analysis complete — {result.insertions_made} toolchange locations will be modified. "
                "Click Generate G-Code to save.",
                "success",
            )

    def _on_processing_error(self, message):
        self._hide_progress()
        self._set_buttons_state("normal")
        self._set_status(f"Error: {message}", "error")

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _set_buttons_state(self, state):
        self.edit_btn.configure(state=state)
        self.gen_btn.configure(state=state)
        self.pick_btn.configure(state=state)

    def _show_progress(self):
        self.progress_bar.set(0)
        self.progress_label.configure(text="0%")
        self.progress_bar.pack(side="left")
        self.progress_label.pack(side="left", padx=(10, 0))

    def _hide_progress(self):
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()

    def _reset_time_display(self):
        for lbl in self.time_value_labels:
            lbl.configure(text="--", text_color=T.TEXT_WHITE)

    def _set_status(self, msg, level):
        color_map = {
            "success": T.NEON_GREEN,
            "error":   T.NEON_RED,
            "warning": T.NEON_ORANGE,
            "dim":     T.TEXT_LABEL,
        }
        self.status_label.configure(
            text=msg,
            text_color=color_map.get(level, T.TEXT_VALUE),
        )
