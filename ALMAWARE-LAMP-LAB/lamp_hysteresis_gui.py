#!/usr/bin/env python3
"""Safe serial GUI for the ALMAWARE 12 V incandescent-bulb experiment.

The GUI plots measured average bulb voltage versus average current.  This is a
volatile thermal-hysteresis experiment, not proof of an ideal memristor.
"""

from __future__ import annotations

import csv
import queue
import statistics
import threading
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import serial
import serial.tools.list_ports


BAUD = 115200
ROOT_DIR = Path(__file__).resolve().parent
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


class LampLab(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ALMAWARE Lamp Lab — thermal hysteresis")
        self.geometry("1120x760")
        self.minsize(960, 660)
        self.configure(bg="#f4f8fb")

        self.ser: serial.Serial | None = None
        self.reader: threading.Thread | None = None
        self.stop_reader = threading.Event()
        self.lines: queue.Queue[str] = queue.Queue()
        self.log_file = None
        self.log_path: Path | None = None
        self.rows: list[dict[str, float | str]] = []
        self.sweep_points: list[tuple[float, float, str, int]] = []

        self.port_var = tk.StringVar()
        self.max_var = tk.IntVar(value=60)
        self.shunt_var = tk.StringVar(value="1.000")
        self.status_var = tk.StringVar(value="Disconnected — 12 V must remain OFF")
        self.metric_var = tk.StringVar(value="No measured sweep")
        self.safety_vars = [tk.BooleanVar(value=False) for _ in range(4)]

        self._build_ui()
        self.refresh_ports()
        self.after(40, self._drain_lines)
        self.protocol("WM_DELETE_WINDOW", self.close_app)

    def _build_ui(self) -> None:
        title = tk.Label(
            self,
            text="ALMAWARE 12 V LAMP LAB",
            font=("Segoe UI", 22, "bold"),
            fg="#073b5c",
            bg="#f4f8fb",
        )
        title.pack(anchor="w", padx=22, pady=(16, 0))
        subtitle = tk.Label(
            self,
            text="Measured thermal hysteresis • default OFF • no automatic run",
            font=("Segoe UI", 11),
            fg="#42677c",
            bg="#f4f8fb",
        )
        subtitle.pack(anchor="w", padx=24, pady=(0, 12))

        body = tk.Frame(self, bg="#f4f8fb")
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        left = tk.Frame(body, bg="white", bd=1, relief="solid", width=335)
        left.pack(side="left", fill="y", padx=(0, 14))
        left.pack_propagate(False)
        right = tk.Frame(body, bg="white", bd=1, relief="solid")
        right.pack(side="left", fill="both", expand=True)

        tk.Label(left, text="1. Serial connection", font=("Segoe UI", 12, "bold"),
                 bg="white", fg="#073b5c").pack(anchor="w", padx=14, pady=(14, 7))
        ports = tk.Frame(left, bg="white")
        ports.pack(fill="x", padx=14)
        self.port_box = ttk.Combobox(ports, textvariable=self.port_var, state="readonly")
        self.port_box.pack(side="left", fill="x", expand=True)
        ttk.Button(ports, text="Refresh", command=self.refresh_ports).pack(side="left", padx=(6, 0))
        self.connect_button = ttk.Button(left, text="CONNECT (12 V OFF)", command=self.toggle_connection)
        self.connect_button.pack(fill="x", padx=14, pady=8)

        tk.Label(left, text="2. Hardware interlocks", font=("Segoe UI", 12, "bold"),
                 bg="white", fg="#073b5c").pack(anchor="w", padx=14, pady=(10, 5))
        safety_text = [
            "12 V incandescent bulb ≤ 5 W (not LED)",
            "Isolated PSU limited to 0.8 A",
            "1 A time-delay fuse installed in +12 V",
            "Power shunt + common GND + MOSFET wiring checked",
        ]
        for var, text in zip(self.safety_vars, safety_text):
            tk.Checkbutton(
                left, text=text, variable=var, anchor="w", justify="left",
                wraplength=295, bg="white", activebackground="white",
                font=("Segoe UI", 9), command=self._update_arm_state,
            ).pack(fill="x", padx=14, pady=2)

        max_row = tk.Frame(left, bg="white")
        max_row.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(max_row, text="First-run PWM ceiling:", bg="white").pack(side="left")
        tk.Spinbox(max_row, from_=20, to=100, width=5, textvariable=self.max_var).pack(side="right")
        shunt_row = tk.Frame(left, bg="white")
        shunt_row.pack(fill="x", padx=14, pady=4)
        tk.Label(shunt_row, text="Shunt resistance (ohm):", bg="white").pack(side="left")
        tk.Entry(shunt_row, width=7, textvariable=self.shunt_var).pack(side="right")

        tk.Label(left, text="3. Experiment", font=("Segoe UI", 12, "bold"),
                 bg="white", fg="#073b5c").pack(anchor="w", padx=14, pady=(12, 5))
        self.status_button = ttk.Button(left, text="STATUS", command=lambda: self.send("STATUS"))
        self.status_button.pack(fill="x", padx=14, pady=3)
        self.sweep_button = ttk.Button(left, text="START HYSTERESIS SWEEP", command=self.start_sweep)
        self.sweep_button.pack(fill="x", padx=14, pady=3)
        self.memory_button = ttk.Button(left, text="THERMAL MEMORY TEST", command=self.start_memory)
        self.memory_button.pack(fill="x", padx=14, pady=3)
        self.stop_button = tk.Button(
            left, text="STOP / MOSFET OFF", command=lambda: self.send("STOP"),
            bg="#c62828", fg="white", activebackground="#8e0000",
            activeforeground="white", font=("Segoe UI", 11, "bold"), bd=0,
        )
        self.stop_button.pack(fill="x", padx=14, pady=(10, 4), ipady=7)
        ttk.Button(left, text="EXPORT LOOP SVG", command=self.export_svg).pack(fill="x", padx=14, pady=3)

        tk.Label(
            left,
            textvariable=self.status_var,
            bg="#eaf4f8", fg="#073b5c", wraplength=295, justify="left",
            font=("Segoe UI", 9, "bold"), padx=8, pady=8,
        ).pack(fill="x", padx=14, pady=(14, 4))
        tk.Label(
            left,
            text="The firmware current watchdog is backup only. The fuse and PSU current limit are mandatory.",
            bg="white", fg="#7a3e00", wraplength=295, justify="left",
            font=("Segoe UI", 9),
        ).pack(fill="x", padx=14, pady=6)

        plot_header = tk.Frame(right, bg="white")
        plot_header.pack(fill="x", padx=14, pady=(12, 2))
        tk.Label(plot_header, text="I–V thermal loop", font=("Segoe UI", 14, "bold"),
                 bg="white", fg="#073b5c").pack(side="left")
        tk.Label(plot_header, textvariable=self.metric_var, font=("Segoe UI", 10),
                 bg="white", fg="#4f6c7b").pack(side="right")
        self.canvas = tk.Canvas(right, bg="#fbfdff", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=12, pady=8)
        self.canvas.bind("<Configure>", lambda _event: self.draw_plot())
        self.console = tk.Text(right, height=9, bg="#071c2a", fg="#c7ecff",
                               insertbackground="white", font=("Consolas", 9), wrap="none")
        self.console.pack(fill="x", padx=12, pady=(0, 12))
        self._set_controls(False)

    def refresh_ports(self) -> None:
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_box["values"] = ports
        if ports and self.port_var.get() not in ports:
            self.port_var.set(ports[0])
        if not ports:
            self.port_var.set("")

    def toggle_connection(self) -> None:
        if self.ser and self.ser.is_open:
            self.disconnect()
            return
        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("No port", "No serial port selected.")
            return
        try:
            self.ser = serial.Serial(port, BAUD, timeout=0.25, write_timeout=1)
        except serial.SerialException as exc:
            messagebox.showerror("Connection failed", str(exc))
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = LOG_DIR / f"lamp-{stamp}.csv"
        self.log_file = self.log_path.open("w", encoding="utf-8", newline="")
        self.stop_reader.clear()
        self.reader = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader.start()
        self.connect_button.configure(text="DISCONNECT")
        self.status_var.set(f"Connected to {port}; waiting for Arduino reset")
        self._set_controls(True)
        self.after(2200, lambda: self.send("STATUS"))

    def disconnect(self) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"STOP\n")
                self.ser.flush()
            except serial.SerialException:
                pass
        self.stop_reader.set()
        if self.ser:
            try:
                self.ser.close()
            except serial.SerialException:
                pass
        self.ser = None
        if self.log_file:
            self.log_file.close()
            self.log_file = None
        self.connect_button.configure(text="CONNECT (12 V OFF)")
        self.status_var.set("Disconnected — MOSFET command sent OFF")
        self._set_controls(False)

    def _reader_loop(self) -> None:
        assert self.ser is not None
        while not self.stop_reader.is_set() and self.ser.is_open:
            try:
                raw = self.ser.readline()
            except serial.SerialException as exc:
                self.lines.put(f"# SERIAL ERROR {exc}")
                return
            if not raw:
                continue
            line = raw.decode("utf-8", "replace").strip()
            if self.log_file:
                self.log_file.write(line + "\n")
                self.log_file.flush()
            self.lines.put(line)

    def _drain_lines(self) -> None:
        changed = False
        while True:
            try:
                line = self.lines.get_nowait()
            except queue.Empty:
                break
            self.console.insert("end", line + "\n")
            self.console.see("end")
            changed = self._parse_line(line) or changed
        if changed:
            self.draw_plot()
        self.after(40, self._drain_lines)

    def _parse_line(self, line: str) -> bool:
        if line.startswith("#"):
            self.status_var.set(line[2:] if line.startswith("# ") else line)
            if "SWEEP begin" in line:
                self.rows.clear()
                self.sweep_points.clear()
            if "SWEEP complete" in line:
                self._update_metrics()
                self.export_svg(auto=True)
            return False
        parts = next(csv.reader([line]))
        if len(parts) != 11 or parts[0] == "ms":
            return False
        try:
            row = {
                "ms": float(parts[0]), "test": parts[1], "phase": parts[2],
                "trial": float(parts[3]), "duty": int(parts[4]),
                "bus_V": float(parts[5]), "drain_V": float(parts[6]),
                "bulb_V": float(parts[7]), "current_mA": float(parts[8]),
                "power_mW": float(parts[9]), "R_ohm": float(parts[10]),
            }
        except ValueError:
            return False
        self.rows.append(row)
        if row["test"] == "sweep":
            self.sweep_points.append((row["bulb_V"], row["current_mA"], row["phase"], row["duty"]))
            return True
        return False

    def _set_controls(self, connected: bool) -> None:
        state = "normal" if connected else "disabled"
        self.status_button.configure(state=state)
        self.stop_button.configure(state=state)
        self._update_arm_state()

    def _armed(self) -> bool:
        return bool(self.ser and self.ser.is_open and all(v.get() for v in self.safety_vars))

    def _update_arm_state(self) -> None:
        state = "normal" if self._armed() else "disabled"
        self.sweep_button.configure(state=state)
        self.memory_button.configure(state=state)

    def send(self, command: str) -> None:
        if not self.ser or not self.ser.is_open:
            messagebox.showwarning("Disconnected", "Connect to the Arduino first.")
            return
        try:
            self.ser.write((command.strip() + "\n").encode("ascii"))
            self.ser.flush()
            self.console.insert("end", f"> {command}\n")
            self.console.see("end")
        except serial.SerialException as exc:
            messagebox.showerror("Serial write failed", str(exc))

    def _safe_max(self) -> int:
        try:
            value = int(self.max_var.get())
        except (TypeError, ValueError):
            value = 60
        return max(20, min(100, value))

    def start_sweep(self) -> None:
        if not self._armed():
            messagebox.showwarning("Not armed", "Confirm all four hardware checks first.")
            return
        self.rows.clear()
        self.sweep_points.clear()
        self.send(f"RSHUNT {self._safe_shunt():.4f}")
        self.after(100, lambda: self.send(f"MAX {self._safe_max()}"))
        self.after(220, lambda: self.send("SWEEP"))

    def start_memory(self) -> None:
        if not self._armed():
            messagebox.showwarning("Not armed", "Confirm all four hardware checks first.")
            return
        self.send(f"RSHUNT {self._safe_shunt():.4f}")
        self.after(100, lambda: self.send(f"MAX {self._safe_max()}"))
        self.after(220, lambda: self.send("MEMORY"))

    def _safe_shunt(self) -> float:
        try:
            value = float(self.shunt_var.get())
        except (TypeError, ValueError):
            value = 1.0
        value = max(0.20, min(10.0, value))
        self.shunt_var.set(f"{value:.4f}")
        return value

    def _plot_bounds(self) -> tuple[float, float]:
        if not self.sweep_points:
            return 12.0, 500.0
        xmax = max(1.0, max(p[0] for p in self.sweep_points) * 1.08)
        ymax = max(10.0, max(p[1] for p in self.sweep_points) * 1.08)
        return xmax, ymax

    def draw_plot(self) -> None:
        c = self.canvas
        c.delete("all")
        w = max(300, c.winfo_width())
        h = max(260, c.winfo_height())
        l, r, t, b = 72, 24, 24, 58
        pw, ph = w - l - r, h - t - b
        xmax, ymax = self._plot_bounds()
        c.create_rectangle(l, t, l + pw, t + ph, outline="#a9c3d1", fill="#fbfdff")
        for i in range(6):
            x = l + pw * i / 5
            y = t + ph * i / 5
            c.create_line(x, t, x, t + ph, fill="#e6eef3")
            c.create_line(l, y, l + pw, y, fill="#e6eef3")
            c.create_text(x, t + ph + 18, text=f"{xmax*i/5:.1f}", fill="#4f6c7b")
            c.create_text(l - 30, t + ph - ph*i/5, text=f"{ymax*i/5:.0f}", fill="#4f6c7b")
        c.create_text(l + pw/2, h - 18, text="Average voltage across bulb (V)", fill="#073b5c")
        c.create_text(18, t + ph/2, text="Current (mA)", angle=90, fill="#073b5c")
        colors = {"up": "#f57c00", "down": "#087ea4"}
        previous: dict[str, tuple[float, float] | None] = {"up": None, "down": None}
        for voltage, current, phase, _duty in self.sweep_points:
            x = l + (voltage / xmax) * pw
            y = t + ph - (current / ymax) * ph
            color = colors.get(phase, "#6a6a6a")
            if previous.get(phase):
                px, py = previous[phase]  # type: ignore[misc]
                c.create_line(px, py, x, y, fill=color, width=2)
            previous[phase] = (x, y)
        c.create_line(l + 18, t + 16, l + 48, t + 16, fill=colors["up"], width=3)
        c.create_text(l + 82, t + 16, text="PWM up", fill="#4f6c7b")
        c.create_line(l + 130, t + 16, l + 160, t + 16, fill=colors["down"], width=3)
        c.create_text(l + 202, t + 16, text="PWM down", fill="#4f6c7b")

    def _update_metrics(self) -> None:
        groups: dict[tuple[str, int], list[float]] = defaultdict(list)
        for _v, current, phase, duty in self.sweep_points:
            groups[(phase, duty)].append(current)
        common = sorted({d for phase, d in groups if phase == "up"} &
                        {d for phase, d in groups if phase == "down"})
        gaps = []
        for duty in common:
            up = statistics.median(groups[("up", duty)])
            down = statistics.median(groups[("down", duty)])
            gaps.append(abs(down - up))
        if gaps:
            self.metric_var.set(f"median branch gap: {statistics.median(gaps):.2f} mA")
        else:
            self.metric_var.set("Incomplete up/down sweep")

    def export_svg(self, auto: bool = False) -> None:
        if not self.sweep_points:
            if not auto:
                messagebox.showinfo("No loop", "Run a complete SWEEP first.")
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = LOG_DIR / f"lamp-loop-{stamp}.svg"
        width, height = 1000, 700
        l, r, t, b = 100, 45, 60, 90
        pw, ph = width - l - r, height - t - b
        xmax, ymax = self._plot_bounds()
        colors = {"up": "#f57c00", "down": "#087ea4"}
        phase_points: dict[str, list[str]] = {"up": [], "down": []}
        for voltage, current, phase, _duty in self.sweep_points:
            if phase not in phase_points:
                continue
            x = l + voltage / xmax * pw
            y = t + ph - current / ymax * ph
            phase_points[phase].append(f"{x:.1f},{y:.1f}")
        grid = []
        for i in range(6):
            x = l + pw*i/5
            y = t + ph*i/5
            grid.append(f'<line x1="{x:.1f}" y1="{t}" x2="{x:.1f}" y2="{t+ph}"/>')
            grid.append(f'<line x1="{l}" y1="{y:.1f}" x2="{l+pw}" y2="{y:.1f}"/>')
        polylines = "".join(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{colors[phase]}" stroke-width="4"/>'
            for phase, points in phase_points.items() if points
        )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="#fbfdff"/>
<text x="{l}" y="35" font-family="Segoe UI,Arial" font-size="24" font-weight="700" fill="#073b5c">ALMAWARE 12 V lamp — measured thermal hysteresis</text>
<g stroke="#e1ebf0" stroke-width="1">{"".join(grid)}</g>
<rect x="{l}" y="{t}" width="{pw}" height="{ph}" fill="none" stroke="#8fb1c3"/>
{polylines}
<text x="{width/2}" y="{height-30}" text-anchor="middle" font-family="Segoe UI,Arial" font-size="18" fill="#073b5c">Average voltage across bulb (V), 0 to {xmax:.2f}</text>
<text x="28" y="{height/2}" transform="rotate(-90 28 {height/2})" text-anchor="middle" font-family="Segoe UI,Arial" font-size="18" fill="#073b5c">Current (mA), 0 to {ymax:.1f}</text>
<text x="{l}" y="{height-58}" font-family="Segoe UI,Arial" font-size="14" fill="#5b7280">Orange: PWM up • Blue: PWM down • Volatile thermal memory, not an ideal memristor</text>
</svg>'''
        path.write_text(svg, encoding="utf-8")
        self.status_var.set(f"Saved plot: {path.name}")
        if not auto:
            messagebox.showinfo("Saved", str(path))

    def close_app(self) -> None:
        self.disconnect()
        self.destroy()


if __name__ == "__main__":
    LampLab().mainloop()
