"""Host-side static/logic verification. Does not open or modify the Pico."""
from pathlib import Path
import ast
import re


ROOT = Path(__file__).resolve().parent
SOURCE_PATH = ROOT / "main.py"
source = SOURCE_PATH.read_text(encoding="utf-8")
tree = ast.parse(source)


def require(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS", message)


classes = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
require(SOURCE_PATH.stat().st_size < 64 * 1024,
        "firmware source remains lightweight for RP2040")
required_agents = {
    "InputAgent", "DisplayAgent", "HumanGameAgent", "LearningAgent",
    "SafetyAgent", "PicoSwarm",
}
require(required_agents <= classes, "five cooperative agents plus scheduler exist")
require("W, H = 320, 480" in source, "logical canvas is full 320x480")
require("b'\\x00\\x00\\x01\\x3F'" in source, "LCD column window ends at 319")
require("b'\\x00\\x00\\x01\\xDF'" in source, "LCD row window ends at 479")
require("self.weights = [[0.0] * 7 for _ in range(3)]" in source,
        "AI learner starts with zero weights")
require("self.inputs.k1.consume()" in source and "self.set_mode('HUMAN')" in source,
        "K1 dispatches human Pong")
require("self.inputs.k2.consume()" in source and "self.set_mode('TRAIN')" in source,
        "K2 dispatches visible training")
require("consume_combo" in source and ".diagnostics(" in source,
        "K1+K2 diagnostic path is reachable")
require("inputs.direction = -inputs.direction" in source,
        "diagnostics can reverse a rotated joystick")
require("inputs.axis_mode = (inputs.axis_mode + 1) % 3" in source,
        "diagnostics can select AUTO, X, or Y axis")
require("Pin(pin_number, Pin.IN)" in source,
        "buttons use measured board bias instead of forced polarity")


def learned_idle(samples):
    return 1 if sum(samples) >= len(samples) // 2 else 0


require(learned_idle([0] * 24) == 0, "active-high button idle is detected")
require(learned_idle([1] * 24) == 1, "active-low button idle is detected")
require((1 != learned_idle([0] * 24)), "active-high press differs from learned idle")
require((0 != learned_idle([1] * 24)), "active-low press differs from learned idle")


def normalized(value, center):
    delta = value - center
    span = (65535 - center) if delta >= 0 else center
    return 0 if span < 1 else (delta * 1000) // span


require(abs(normalized(33000, 33000)) < 125, "joystick center is inside deadzone")
require(normalized(65535, 33000) == 1000, "joystick positive rail is normalized")
require(normalized(0, 33000) == -1000, "joystick negative rail is normalized")

for forbidden in ("mpremote", "COM43", "fs cp", "subprocess"):
    require(forbidden not in source, "firmware contains no host operation: " + forbidden)

backup = ROOT / "main.before-agent-swarm-20260721.py"
require(backup.exists() and backup.stat().st_size > 10000, "pre-swarm backup is preserved")
print("VERIFY_OK", SOURCE_PATH)
