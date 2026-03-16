import customtkinter as ctk
from tkinter import filedialog
import threading
import os

from gcode_processor import (
    process_lines, write_output,
    parse_original_time, format_seconds,
    find_unique_output_path,
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class GCodeEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Bambu G-Code Editor")
        self.geometry("620x610")
        self.resizable(False, False)

        self.input_path = None
        self.result = None

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 20, "pady": 6}

        # --- Row 1: File selection ---
        file_frame = ctk.CTkFrame(self, fg_color="transparent")
        file_frame.pack(fill="x", **pad)

        self.pick_btn = ctk.CTkButton(
            file_frame, text="Select .gcode File...",
            width=180, command=self._pick_file
        )
        self.pick_btn.pack(side="left")

        self.file_label = ctk.CTkLabel(
            file_frame, text="No file selected",
            anchor="w", wraplength=360,
            text_color="gray"
        )
        self.file_label.pack(side="left", padx=(12, 0), fill="x", expand=True)

        # --- Row 2: Retraction distance ---
        ret_frame = ctk.CTkFrame(self, fg_color="transparent")
        ret_frame.pack(fill="x", **pad)

        ctk.CTkLabel(ret_frame, text="Retraction Distance (mm):").pack(side="left")

        self.retraction_entry = ctk.CTkEntry(
            ret_frame, width=90, placeholder_text="e.g. 3.5"
        )
        self.retraction_entry.pack(side="left", padx=(12, 0))
        self.retraction_entry.bind("<KeyRelease>", self._on_retraction_changed)

        self.retraction_hint = ctk.CTkLabel(
            ret_frame, text="", text_color="gray", width=200, anchor="w"
        )
        self.retraction_hint.pack(side="left", padx=(10, 0))

        # --- Row 3: Temperature checkbox ---
        temp_outer = ctk.CTkFrame(self, fg_color="transparent")
        temp_outer.pack(fill="x", padx=20, pady=(2, 0))

        self.temp_var = ctk.BooleanVar(value=False)
        self.temp_check = ctk.CTkCheckBox(
            temp_outer,
            text="Decrease Temperature Before Travel",
            variable=self.temp_var,
            command=self._on_temp_toggled,
            font=ctk.CTkFont(size=13),
        )
        self.temp_check.pack(side="top", anchor="w")

        # Temperature input sub-row (indented, disabled until checkbox ticked)
        temp_inputs = ctk.CTkFrame(temp_outer, fg_color="transparent")
        temp_inputs.pack(fill="x", padx=(28, 0), pady=(6, 4))

        ctk.CTkLabel(temp_inputs, text="Cool to:").pack(side="left")
        self.cool_temp_entry = ctk.CTkEntry(
            temp_inputs, width=70, placeholder_text="200"
        )
        self.cool_temp_entry.insert(0, "200")
        self.cool_temp_entry.configure(state="disabled")
        self.cool_temp_entry.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(temp_inputs, text="°C").pack(side="left")

        ctk.CTkLabel(temp_inputs, text="    Reheat to:").pack(side="left")
        self.reheat_temp_entry = ctk.CTkEntry(
            temp_inputs, width=70, placeholder_text="270"
        )
        self.reheat_temp_entry.insert(0, "270")
        self.reheat_temp_entry.configure(state="disabled")
        self.reheat_temp_entry.pack(side="left", padx=(6, 2))
        ctk.CTkLabel(temp_inputs, text="°C").pack(side="left")

        # --- Separator ---
        ctk.CTkFrame(self, height=2, fg_color="#333333").pack(fill="x", padx=20, pady=6)

        # --- Row 4: Analyse File + Generate G-Code buttons ---
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=4)

        self.edit_btn = ctk.CTkButton(
            btn_frame, text="Analyse File",
            width=200, height=38,
            command=self._on_edit_click,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.edit_btn.pack(side="left")

        self.gen_btn = ctk.CTkButton(
            btn_frame, text="Generate G-Code",
            width=200, height=38,
            command=self._on_generate_click,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2D6A4F", hover_color="#1B4332",
        )
        self.gen_btn.pack(side="left", padx=(16, 0))

        # --- Row 5: Progress bar (hidden until needed) ---
        self.progress_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=20, pady=(4, 0))

        self.progress_bar = ctk.CTkProgressBar(self.progress_frame, width=500)
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(self.progress_frame, text="0%", width=40)

        self._hide_progress()

        # --- Row 6: Time comparison ---
        ctk.CTkFrame(self, height=2, fg_color="#333333").pack(fill="x", padx=20, pady=6)

        time_outer = ctk.CTkFrame(self)
        time_outer.pack(fill="x", padx=20, pady=4)

        headers = ["Original Time", "Edited Time", "Additional Time"]
        self.time_value_labels = []

        for col, header in enumerate(headers):
            col_frame = ctk.CTkFrame(time_outer, fg_color="transparent")
            col_frame.grid(row=0, column=col, padx=20, pady=6, sticky="nsew")
            time_outer.columnconfigure(col, weight=1)

            ctk.CTkLabel(
                col_frame, text=header,
                font=ctk.CTkFont(size=12), text_color="gray"
            ).pack()

            val_label = ctk.CTkLabel(
                col_frame, text="--",
                font=ctk.CTkFont(size=18, weight="bold"),
            )
            val_label.pack()
            self.time_value_labels.append(val_label)

        # --- Row 7: Status label ---
        ctk.CTkFrame(self, height=2, fg_color="#333333").pack(fill="x", padx=20, pady=6)

        self.status_label = ctk.CTkLabel(
            self, text="Select a .gcode file and enter a retraction distance to begin.",
            wraplength=580, anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.status_label.pack(fill="x", padx=20, pady=6)

    # -------------------------------------------------------------------------
    # File picker
    # -------------------------------------------------------------------------

    def _pick_file(self):
        path = filedialog.askopenfilename(
            title="Select G-Code File",
            filetypes=[("G-Code files", "*.gcode"), ("All files", "*.*")]
        )
        if not path:
            return

        self.input_path = path
        self.result = None
        self.file_label.configure(
            text=os.path.basename(path),
            text_color="white"
        )
        self._reset_time_display()
        self._set_status("File loaded. Enter a retraction distance and click Analyse File.", "gray")

    # -------------------------------------------------------------------------
    # Temperature checkbox toggle
    # -------------------------------------------------------------------------

    def _on_temp_toggled(self):
        state = "normal" if self.temp_var.get() else "disabled"
        self.cool_temp_entry.configure(state=state)
        self.reheat_temp_entry.configure(state=state)

    # -------------------------------------------------------------------------
    # Input validation
    # -------------------------------------------------------------------------

    def _on_retraction_changed(self, event=None):
        raw = self.retraction_entry.get().strip()
        valid, _, value = self._parse_retraction(raw)

        if not raw:
            self.retraction_entry.configure(fg_color=["#343638", "#343638"])
            self.retraction_hint.configure(text="")
            return

        if not valid:
            self.retraction_entry.configure(fg_color="#5C1A1A")
            self.retraction_hint.configure(text="Invalid value", text_color="#FF6B6B")
            return

        if value > 14:
            self.retraction_entry.configure(fg_color="#5C1A1A")
            self.retraction_hint.configure(
                text=f"Warning: {value}mm is a large retraction",
                text_color="#FF6B6B"
            )
        else:
            self.retraction_entry.configure(fg_color=["#343638", "#343638"])
            self.retraction_hint.configure(text="")

    def _parse_retraction(self, raw):
        """Returns (is_valid, error_msg, float_value)."""
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

    def _parse_temperature(self, raw, field_name):
        """Returns (is_valid, error_msg, int_value)."""
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

    def _validate_inputs(self):
        """
        Returns (is_valid, error_msg, retraction_value, cool_temp, reheat_temp).
        """
        if not self.input_path:
            return False, "Please select a .gcode file.", 0.0, 0, 0
        if not os.path.exists(self.input_path):
            return False, f"File not found: {self.input_path}", 0.0, 0, 0
        if not self.input_path.lower().endswith('.gcode'):
            return False, "Selected file must have a .gcode extension.", 0.0, 0, 0

        raw = self.retraction_entry.get().strip()
        ok, msg, ret_val = self._parse_retraction(raw)
        if not ok:
            return False, f"Retraction distance: {msg}", 0.0, 0, 0

        cool_val   = 200
        reheat_val = 270
        if self.temp_var.get():
            ok, msg, cool_val = self._parse_temperature(
                self.cool_temp_entry.get().strip(), "Cool temperature"
            )
            if not ok:
                return False, msg, 0.0, 0, 0

            ok, msg, reheat_val = self._parse_temperature(
                self.reheat_temp_entry.get().strip(), "Reheat temperature"
            )
            if not ok:
                return False, msg, 0.0, 0, 0

        return True, "", ret_val, cool_val, reheat_val

    # -------------------------------------------------------------------------
    # Button handlers
    # -------------------------------------------------------------------------

    def _on_edit_click(self):
        ok, msg, ret_val, cool, reheat = self._validate_inputs()
        if not ok:
            self._set_status(msg, "red")
            return

        self._set_buttons_state("disabled")
        self._show_progress()
        self._set_status("Analysing G-Code...", "gray")
        threading.Thread(
            target=self._run_processing,
            args=(ret_val, cool, reheat, False),
            daemon=True
        ).start()

    def _on_generate_click(self):
        ok, msg, ret_val, cool, reheat = self._validate_inputs()
        if not ok:
            self._set_status(msg, "red")
            return

        self._set_buttons_state("disabled")
        self._show_progress()
        self._set_status("Processing and saving G-Code...", "gray")
        threading.Thread(
            target=self._run_processing,
            args=(ret_val, cool, reheat, True),
            daemon=True
        ).start()

    # -------------------------------------------------------------------------
    # Background processing
    # -------------------------------------------------------------------------

    def _run_processing(self, retraction_value, cool_temp, reheat_temp, save_to_disk):
        try:
            with open(self.input_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            result = process_lines(
                lines,
                retraction_value,
                self.temp_var.get(),
                cool_temp=cool_temp,
                reheat_temp=reheat_temp,
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
        new_secs = result.original_seconds + result.added_seconds
        new_str  = format_seconds(new_secs)
        add_str  = f"+{format_seconds(result.added_seconds)}"

        self.time_value_labels[0].configure(text=orig_str)
        self.time_value_labels[1].configure(text=new_str)
        self.time_value_labels[2].configure(text=add_str, text_color="#FFA500")

        if saved:
            fname = os.path.basename(result.output_path)
            self._set_status(
                f"Saved: {fname}  ({result.insertions_made} toolchange locations modified)",
                "green"
            )
        else:
            self._set_status(
                f"Analysis complete — {result.insertions_made} toolchange locations will be modified. "
                "Click Generate G-Code to save.",
                "green"
            )

    def _on_processing_error(self, message):
        self._hide_progress()
        self._set_buttons_state("normal")
        self._set_status(f"Error: {message}", "red")

    # -------------------------------------------------------------------------
    # UI helpers
    # -------------------------------------------------------------------------

    def _set_buttons_state(self, state):
        self.edit_btn.configure(state=state)
        self.gen_btn.configure(state=state)
        self.pick_btn.configure(state=state)

    def _show_progress(self):
        self.progress_bar.set(0)
        self.progress_label.configure(text="0%")
        self.progress_bar.pack(side="left")
        self.progress_label.pack(side="left", padx=(8, 0))

    def _hide_progress(self):
        self.progress_bar.pack_forget()
        self.progress_label.pack_forget()

    def _reset_time_display(self):
        for label in self.time_value_labels:
            label.configure(text="--", text_color="white")

    def _set_status(self, msg, color):
        color_map = {
            "green": "#4CAF50",
            "red":   "#FF6B6B",
            "gray":  "gray",
        }
        self.status_label.configure(
            text=msg,
            text_color=color_map.get(color, "white")
        )


if __name__ == "__main__":
    app = GCodeEditorApp()
    app.mainloop()
