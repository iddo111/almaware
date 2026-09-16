from __future__ import annotations

import queue
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable, Deque, Dict, List, Optional

from .config import MachineConfig
from .gcode import ValidationResult, validate_program
from .protocol import GrblStatus, parse_status_report


EventCallback = Callable[[str, str], None]
AXIS_WORD = re.compile(r"([XYZ])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


class MachineError(RuntimeError):
    pass


class Simulator:
    def __init__(self, event: EventCallback):
        self.event = event
        self.connected = False
        self.status = GrblStatus(state="Disconnected")
        self._lock = threading.Lock()

    def connect(self) -> None:
        with self._lock:
            self.connected = True
            self.status.state = "Idle"
            self.status.raw = "<Idle|MPos:0.000,0.000,0.000|FS:0,0>"
        self.event("info", "Simulation transport connected")

    def disconnect(self) -> None:
        with self._lock:
            self.connected = False
            self.status.state = "Disconnected"
        self.event("info", "Simulation transport disconnected")

    def realtime(self, command: bytes) -> None:
        with self._lock:
            if command == b"!":
                self.status.state = "Hold"
            elif command == b"~":
                self.status.state = "Idle"
            elif command == b"\x18":
                self.status.state = "Idle"
                self.status.feed = 0.0
            elif command != b"?":
                raise MachineError("Unsupported realtime command")

    def send_line(self, line: str, timeout: float = 5.0) -> str:
        del timeout
        with self._lock:
            if not self.connected:
                raise MachineError("Simulation is not connected")
            if line.startswith("$J="):
                for axis, raw_value in AXIS_WORD.findall(line):
                    index = "XYZ".index(axis)
                    self.status.machine_position[index] += float(raw_value)
                    self.status.work_position[index] += float(raw_value)
            elif line == "$X":
                self.status.state = "Idle"
            elif line == "G10L20P1X0Y0Z0":
                self.status.work_position = [0.0, 0.0, 0.0]
            self.status.state = "Idle"
        time.sleep(0.01)
        return "ok"

    def snapshot(self) -> GrblStatus:
        with self._lock:
            return GrblStatus(
                state=self.status.state,
                substate=self.status.substate,
                machine_position=list(self.status.machine_position),
                work_position=list(self.status.work_position),
                feed=self.status.feed,
                spindle=self.status.spindle,
                pins=self.status.pins,
                raw=self.status.raw,
                fields=dict(self.status.fields),
            )


class SerialGrbl:
    def __init__(self, config: MachineConfig, event: EventCallback):
        self.config = config
        self.event = event
        self.connected = False
        self.status = GrblStatus(state="Disconnected")
        self._serial = None
        self._responses: "queue.Queue[str]" = queue.Queue()
        self._write_lock = threading.Lock()
        self._status_lock = threading.Lock()
        self._stop = threading.Event()
        self._reader: Optional[threading.Thread] = None
        self._poller: Optional[threading.Thread] = None

    def connect(self) -> None:
        try:
            import serial
        except ImportError as exc:
            raise MachineError("pyserial is required for serial mode") from exc
        try:
            self._serial = serial.Serial(
                self.config.serial_port,
                self.config.baud_rate,
                timeout=0.2,
                write_timeout=1.0,
            )
        except Exception as exc:
            raise MachineError(f"Cannot open {self.config.serial_port}: {exc}") from exc
        self._stop.clear()
        self.connected = True
        self._reader = threading.Thread(target=self._read_loop, name="grbl-reader", daemon=True)
        self._poller = threading.Thread(target=self._poll_loop, name="grbl-poller", daemon=True)
        self._reader.start()
        self._poller.start()
        self._serial.write(b"\r\n")
        self.event("info", f"Serial transport opened on {self.config.serial_port}")

    def disconnect(self) -> None:
        self._stop.set()
        self.connected = False
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
        with self._status_lock:
            self.status.state = "Disconnected"
        self.event("info", "Serial transport disconnected")

    def realtime(self, command: bytes) -> None:
        if command not in {b"?", b"!", b"~", b"\x18", b"\x85"}:
            raise MachineError("Unsupported realtime command")
        self._write(command)

    def send_line(self, line: str, timeout: float = 5.0) -> str:
        if "\r" in line or "\n" in line:
            raise MachineError("A GRBL line cannot contain newline characters")
        with self._write_lock:
            while not self._responses.empty():
                try:
                    self._responses.get_nowait()
                except queue.Empty:
                    break
            self._write((line + "\n").encode("ascii"))
            try:
                response = self._responses.get(timeout=timeout)
            except queue.Empty as exc:
                raise MachineError(f"GRBL did not acknowledge: {line}") from exc
            if response.startswith("error:") or response.startswith("ALARM:"):
                raise MachineError(f"GRBL rejected line '{line}': {response}")
            return response

    def snapshot(self) -> GrblStatus:
        with self._status_lock:
            return GrblStatus(
                state=self.status.state,
                substate=self.status.substate,
                machine_position=list(self.status.machine_position),
                work_position=list(self.status.work_position),
                feed=self.status.feed,
                spindle=self.status.spindle,
                pins=self.status.pins,
                raw=self.status.raw,
                fields=dict(self.status.fields),
            )

    def _write(self, payload: bytes) -> None:
        if not self.connected or self._serial is None:
            raise MachineError("Serial transport is not connected")
        try:
            self._serial.write(payload)
        except Exception as exc:
            raise MachineError(f"Serial write failed: {exc}") from exc

    def _read_loop(self) -> None:
        assert self._serial is not None
        while not self._stop.is_set():
            try:
                raw = self._serial.readline()
            except Exception as exc:
                self.event("error", f"Serial read failed: {exc}")
                self.connected = False
                return
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            if not line:
                continue
            if line.startswith("<") and line.endswith(">"):
                try:
                    parsed = parse_status_report(line)
                except ValueError as exc:
                    self.event("warning", f"Malformed status report: {exc}")
                    continue
                with self._status_lock:
                    self.status = parsed
            elif line == "ok" or line.startswith("error:") or line.startswith("ALARM:"):
                self._responses.put(line)
                if line.startswith("ALARM:"):
                    self.event("error", line)
            else:
                self.event("controller", line)

    def _poll_loop(self) -> None:
        while not self._stop.wait(0.25):
            try:
                self._write(b"?")
            except MachineError:
                return


class MachineService:
    REQUIRED_APPROVALS = {
        "operator_present",
        "area_clear",
        "hardware_estop_ready",
        "spindle_power_isolated",
    }

    def __init__(self, config: MachineConfig):
        self.config = config
        self.events: Deque[Dict[str, str]] = deque(maxlen=250)
        self.transport = (
            Simulator(self._event)
            if config.simulation
            else SerialGrbl(config, self._event)
        )
        self.job_lock = threading.Lock()
        self.job_state = "none"
        self.job_progress = 0
        self.job_total = 0
        self.job_name = ""
        self._job_thread: Optional[threading.Thread] = None
        self._abort = threading.Event()
        self._pause = threading.Event()
        self._event("info", "Console started with spindle commands locked")

    def _event(self, level: str, message: str) -> None:
        self.events.appendleft(
            {
                "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "level": level,
                "message": message,
            }
        )

    def connect(self) -> None:
        if self.transport.connected:
            return
        self.transport.connect()

    def disconnect(self) -> None:
        if self.job_state in {"running", "paused"}:
            raise MachineError("Abort the active job before disconnecting")
        self.transport.disconnect()

    def snapshot(self) -> Dict[str, object]:
        status = self.transport.snapshot()
        return {
            "connected": self.transport.connected,
            "simulation": self.config.simulation,
            "spindle_locked": not self.config.spindle_commands_enabled,
            "machine": status.as_dict(),
            "job": {
                "state": self.job_state,
                "name": self.job_name,
                "progress": self.job_progress,
                "total": self.job_total,
            },
            "events": list(self.events)[:80],
        }

    def realtime(self, action: str) -> None:
        command = {
            "status": b"?",
            "hold": b"!",
            "resume": b"~",
            "soft_reset": b"\x18",
            "jog_cancel": b"\x85",
        }.get(action)
        if command is None:
            raise MachineError("Unknown realtime action")
        if action == "soft_reset" and self.job_state in {"running", "paused"}:
            self._abort.set()
        self.transport.realtime(command)
        self._event("warning" if action in {"hold", "soft_reset"} else "info", action.replace("_", " "))

    def jog(self, axis: str, distance_mm: float, feed_mm_min: Optional[float] = None) -> None:
        axis = axis.upper()
        if axis not in {"X", "Y", "Z"}:
            raise MachineError("Jog axis must be X, Y, or Z")
        if not self.transport.connected:
            raise MachineError("Connect the controller before jogging")
        status = self.transport.snapshot()
        if status.state not in {"Idle", "Jog"}:
            raise MachineError(f"Jog is blocked while machine state is {status.state}")
        if distance_mm == 0 or abs(distance_mm) > self.config.max_jog_step_mm:
            raise MachineError(
                f"Jog distance must be non-zero and at most {self.config.max_jog_step_mm:g} mm"
            )
        feed = feed_mm_min or self.config.jog_feed_mm_min
        if feed <= 0 or feed > min(self.config.max_feed_mm_min, 1000.0):
            raise MachineError("Jog feed must be between 0 and 1000 mm/min")
        command = f"$J=G91 G21 {axis}{distance_mm:.3f} F{feed:.1f}"
        self.transport.send_line(command)
        self._event("motion", f"Jog {axis} {distance_mm:+.3f} mm at {feed:.0f} mm/min")

    def home(self) -> None:
        if not self.transport.connected:
            raise MachineError("Connect the controller before homing")
        status = self.transport.snapshot()
        if status.state not in {"Idle", "Alarm"}:
            raise MachineError(f"Homing is blocked while machine state is {status.state}")
        self.transport.send_line("$H", timeout=90.0)
        self._event("motion", "Homing cycle requested")

    def unlock(self) -> None:
        if not self.transport.connected:
            raise MachineError("Connect the controller before unlocking")
        status = self.transport.snapshot()
        if status.state not in {"Idle", "Alarm"}:
            raise MachineError(f"Unlock is blocked while machine state is {status.state}")
        self.transport.send_line("$X")
        self._event("warning", "GRBL alarm unlock requested; position may be untrusted")

    def set_work_zero(self) -> None:
        if not self.transport.connected:
            raise MachineError("Connect the controller before setting work zero")
        status = self.transport.snapshot()
        if status.state != "Idle":
            raise MachineError(f"Work zero is blocked while machine state is {status.state}")
        if self.job_state in {"running", "paused"}:
            raise MachineError("Work zero is blocked while a job is active")
        self.transport.send_line("G10L20P1X0Y0Z0")
        self._event("warning", "Current position set as X/Y/Z work zero")

    def validate(self, source: str) -> ValidationResult:
        return validate_program(
            source,
            (self.config.x_mm, self.config.y_mm, self.config.z_mm),
            self.config.max_feed_mm_min,
            self.config.spindle_commands_enabled,
        )

    def start_job(
        self,
        name: str,
        source: str,
        approvals: Dict[str, object],
    ) -> ValidationResult:
        if not self.transport.connected:
            raise MachineError("Connect the controller before starting a job")
        missing = sorted(key for key in self.REQUIRED_APPROVALS if approvals.get(key) is not True)
        if missing:
            raise MachineError("Preflight acknowledgements missing: " + ", ".join(missing))
        status = self.transport.snapshot()
        if status.state != "Idle":
            raise MachineError(f"Job start is blocked while machine state is {status.state}")
        result = self.validate(source)
        if not result.valid:
            raise MachineError("Job failed validation")
        with self.job_lock:
            if self.job_state in {"running", "paused"}:
                raise MachineError("A job is already active")
            self.job_name = name or "untitled.nc"
            self.job_progress = 0
            self.job_total = len(result.normalized_lines)
            self.job_state = "running"
            self._abort.clear()
            self._pause.clear()
            self._job_thread = threading.Thread(
                target=self._run_job,
                args=(list(result.normalized_lines),),
                name="gcode-stream",
                daemon=True,
            )
            self._job_thread.start()
        self._event("motion", f"Dry-motion job started: {self.job_name}")
        return result

    def pause_job(self) -> None:
        if self.job_state != "running":
            raise MachineError("No running job to pause")
        self._pause.set()
        self.transport.realtime(b"!")
        self.job_state = "paused"
        self._event("warning", "Job feed hold requested")

    def resume_job(self) -> None:
        if self.job_state != "paused":
            raise MachineError("No paused job to resume")
        self.transport.realtime(b"~")
        self._pause.clear()
        self.job_state = "running"
        self._event("motion", "Job resumed")

    def abort_job(self) -> None:
        if self.job_state not in {"running", "paused"}:
            raise MachineError("No active job to abort")
        self._abort.set()
        self._pause.clear()
        self.transport.realtime(b"!")
        self.job_state = "aborting"
        self._event("warning", "Job abort requested; feed hold sent")

    def _run_job(self, lines: List[str]) -> None:
        try:
            for index, line in enumerate(lines, start=1):
                if self._abort.is_set():
                    self.job_state = "aborted"
                    return
                while self._pause.is_set() and not self._abort.wait(0.05):
                    pass
                if self._abort.is_set():
                    self.job_state = "aborted"
                    return
                self.transport.send_line(line, timeout=15.0)
                self.job_progress = index
            self.job_state = "complete"
            self._event("info", f"Job completed: {self.job_name}")
        except Exception as exc:
            self.job_state = "failed"
            self._event("error", f"Job failed at line {self.job_progress + 1}: {exc}")
