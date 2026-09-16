from machine import ADC, Pin
import time

k1 = Pin(15, Pin.IN)
k2 = Pin(14, Pin.IN)
x = ADC(Pin(26))
y = ADC(Pin(27))

start = time.ticks_ms()
x_min = x_max = x.read_u16()
y_min = y_max = y.read_u16()
k1_seen = k2_seen = 0

print("PROBE_START_PRESS_K1_K2_MOVE_JOYSTICK")
while time.ticks_diff(time.ticks_ms(), start) < 20000:
    xv = x.read_u16()
    yv = y.read_u16()
    x_min = min(x_min, xv)
    x_max = max(x_max, xv)
    y_min = min(y_min, yv)
    y_max = max(y_max, yv)
    k1_seen = max(k1_seen, k1.value())
    k2_seen = max(k2_seen, k2.value())
    time.sleep_ms(10)

print("PROBE_RESULT", k1_seen, k2_seen, x_min, x_max, y_min, y_max)
