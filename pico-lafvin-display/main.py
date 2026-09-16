# ============================================================================
# LAFVIN Pico W 320x480 lab - cooperative embedded-agent firmware
#
# K1: human Pong       K2: AI Pong learns visibly from zero
# K1+K2 (hold): live input diagnostics       joystick press: return/home
#
# The "agents" below are small deterministic state machines. They cooperate in
# one bounded scheduler; they are not cloud/LLM processes and need no network.
# MicroPython / RP2040.  ALMAWARE / Diyalna / Quincy.
# ============================================================================
from machine import Pin, SPI, ADC, PWM
import framebuf
import random
import rp2
import time

SCK, MOSI, MISO = 2, 3, 4
CS, DC, RST = 5, 6, 7
BUZZER, RGB_PIN = 13, 12
K1_PIN, K2_PIN = 15, 14
JOY_SW, ADC_X, ADC_Y = 22, 26, 27
W, H = 320, 480


def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


BLACK = 0x0000
WHITE = 0xFFFF
CYAN = 0x07FF
YELLOW = 0xFFE0
LIME = rgb565(90, 255, 130)
GOLD = rgb565(212, 160, 23)
BLUE = rgb565(70, 135, 255)
PINK = rgb565(255, 80, 145)
GREY = rgb565(58, 66, 82)
DARK = rgb565(3, 11, 25)
ORANGE = rgb565(255, 145, 35)
RED = rgb565(255, 65, 65)


# ---------------------------------------------------------------- LCD agent --
class LCD:
    def __init__(self, spi, cs, dc, rst):
        self.spi = spi
        self.cs = Pin(cs, Pin.OUT, value=1)
        self.dc = Pin(dc, Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1)
        self.w, self.h = W, H
        self._reset()
        self._init()

    def _cmd(self, command, data=None):
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([command]))
        if data is not None:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _reset(self):
        self.rst(1)
        time.sleep_ms(20)
        self.rst(0)
        time.sleep_ms(40)
        self.rst(1)
        time.sleep_ms(120)

    def _init(self):
        # LAFVIN's working panel sequence, with the complete 320x480 window.
        self._cmd(0xCF, b'\x00\x83\x30')
        self._cmd(0xED, b'\x64\x03\x12\x81')
        self._cmd(0xE8, b'\x85\x01\x79')
        self._cmd(0xCB, b'\x39\x2C\x00\x34\x02')
        self._cmd(0xF7, b'\x20')
        self._cmd(0xEA, b'\x00\x00')
        self._cmd(0xC0, b'\x26')
        self._cmd(0xC1, b'\x11')
        self._cmd(0xC5, b'\x35\x3E')
        self._cmd(0xC7, b'\xBE')
        self._cmd(0x36, b'\x28')
        self._cmd(0x3A, b'\x05')
        self._cmd(0xB1, b'\x00\x1B')
        self._cmd(0xF2, b'\x08')
        self._cmd(0x26, b'\x01')
        self._cmd(0xE0, b'\x1F\x1A\x18\x0A\x0F\x06\x45\x87\x32\x0A\x07\x02\x07\x05\x00')
        self._cmd(0xE1, b'\x00\x25\x27\x05\x10\x09\x3A\x78\x4D\x05\x18\x0D\x38\x3A\x1F')
        self._cmd(0x2A, b'\x00\x00\x01\x3F')  # columns 0..319
        self._cmd(0x2B, b'\x00\x00\x01\xDF')  # rows 0..479
        self._cmd(0xB7, b'\x07')
        self._cmd(0xB6, b'\x0A\x82\x27\x00')
        self._cmd(0x11)
        time.sleep_ms(120)
        self._cmd(0x29)
        time.sleep_ms(80)
        self._cmd(0x36, b'\x48')
        self._cmd(0x21)

    def _window(self, x0, y0, x1, y1):
        self._cmd(0x2A, bytes([x0 >> 8, x0 & 255, x1 >> 8, x1 & 255]))
        self._cmd(0x2B, bytes([y0 >> 8, y0 & 255, y1 >> 8, y1 & 255]))
        self._cmd(0x2C)

    def fill_rect(self, x, y, w, h, color):
        if x < 0:
            w += x
            x = 0
        if y < 0:
            h += y
            y = 0
        if x + w > self.w:
            w = self.w - x
        if y + h > self.h:
            h = self.h - y
        if w <= 0 or h <= 0:
            return
        self._window(x, y, x + w - 1, y + h - 1)
        row = bytearray(w * 2)
        hi, lo = color >> 8, color & 255
        for index in range(0, len(row), 2):
            row[index] = hi
            row[index + 1] = lo
        self.cs(0)
        self.dc(1)
        for _ in range(h):
            self.spi.write(row)
        self.cs(1)

    def fill(self, color):
        self.fill_rect(0, 0, self.w, self.h, color)

    def _blit(self, buf, x, y, w, h):
        self._window(x, y, x + w - 1, y + h - 1)
        self.cs(0)
        self.dc(1)
        self.spi.write(buf)
        self.cs(1)

    def text(self, message, x, y, fg=WHITE, bg=BLACK, scale=1):
        width = len(message) * 8
        if width <= 0:
            return
        buf = bytearray(width * 8 * 2)
        fb = framebuf.FrameBuffer(buf, width, 8, framebuf.RGB565)
        fb.fill(bg)
        fb.text(message, 0, 0, fg)
        if scale == 1:
            self._blit(buf, x, y, width, 8)
            return
        for source_y in range(8):
            line = bytearray(width * scale * 2)
            for source_x in range(width):
                source = (source_y * width + source_x) * 2
                for repeat in range(scale):
                    target = (source_x * scale + repeat) * 2
                    line[target] = buf[source]
                    line[target + 1] = buf[source + 1]
            self._window(x, y + source_y * scale,
                         x + width * scale - 1,
                         y + source_y * scale + scale - 1)
            self.cs(0)
            self.dc(1)
            for _ in range(scale):
                self.spi.write(line)
            self.cs(1)

    def line(self, x0, y0, x1, y1, color, thickness=1):
        dx, sx = abs(x1 - x0), 1 if x0 < x1 else -1
        dy, sy = -abs(y1 - y0), 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            self.fill_rect(x0, y0, thickness, thickness, color)
            if x0 == x1 and y0 == y1:
                return
            twice = error * 2
            if twice >= dy:
                error += dy
                x0 += sx
            if twice <= dx:
                error += dx
                y0 += sy


# --------------------------------------------------------------- RGB/buzzer --
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW,
             out_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopull=True, pull_thresh=24)
def _ws2812():
    label('bitloop')
    out(x, 1).side(0)[2]
    jmp(not_x, 'do_zero').side(1)[1]
    jmp('bitloop').side(1)[4]
    label('do_zero')
    nop().side(0)[4]


_rgb_sm = rp2.StateMachine(0, _ws2812, freq=8_000_000,
                           sideset_base=Pin(RGB_PIN))
_rgb_sm.active(1)
_buzzer = PWM(Pin(BUZZER))
_buzzer.duty_u16(0)


def rgb(r, g, b):
    _rgb_sm.put((g << 16) | (r << 8) | b, 8)


def chirp(frequency, duration=18):
    _buzzer.freq(frequency)
    _buzzer.duty_u16(6500)
    time.sleep_ms(duration)
    _buzzer.duty_u16(0)


# -------------------------------------------------------------- input agent --
class Button:
    """Debounced button whose idle polarity is learned at boot."""
    def __init__(self, pin_number):
        # Board already provides biasing; no hard-coded pull/polarity.
        self.pin = Pin(pin_number, Pin.IN)
        ones = 0
        for _ in range(24):
            ones += self.pin.value()
            time.sleep_ms(2)
        self.idle = 1 if ones >= 12 else 0
        self.raw = self.pin.value()
        self.stable = self.raw
        self.changed_at = time.ticks_ms()
        self.down = False
        self.press_event = False
        self.release_event = False

    def sample(self, now):
        value = self.pin.value()
        if value != self.raw:
            self.raw = value
            self.changed_at = now
        if value != self.stable and time.ticks_diff(now, self.changed_at) >= 24:
            old_down = self.down
            self.stable = value
            self.down = value != self.idle
            self.press_event = self.down and not old_down
            self.release_event = old_down and not self.down

    def consume(self):
        event = self.press_event
        self.press_event = False
        return event


class InputAgent:
    def __init__(self):
        self.k1 = Button(K1_PIN)
        self.k2 = Button(K2_PIN)
        self.sw = Button(JOY_SW)
        self.x_adc = ADC(Pin(ADC_X))
        self.y_adc = ADC(Pin(ADC_Y))
        self.x = self._average(self.x_adc)
        self.y = self._average(self.y_adc)
        self.cx, self.cy = self.x, self.y
        self.x_min = self.x_max = self.x
        self.y_min = self.y_max = self.y
        self.axis = 'X'
        self.axis_mode = 0  # 0=AUTO, 1=X, 2=Y
        self.direction = 1
        self.command = 0
        self.combo_since = None
        self.combo_event = False

    def _average(self, adc, count=12):
        total = 0
        for _ in range(count):
            total += adc.read_u16()
        return total // count

    @staticmethod
    def _normal(value, center):
        delta = value - center
        span = (65535 - center) if delta >= 0 else center
        if span < 1:
            return 0
        return (delta * 1000) // span

    def step(self, now):
        self.k1.sample(now)
        self.k2.sample(now)
        self.sw.sample(now)
        # IIR filtering removes ADC jitter without lagging human movement.
        self.x = (self.x * 3 + self.x_adc.read_u16()) // 4
        self.y = (self.y * 3 + self.y_adc.read_u16()) // 4
        self.x_min, self.x_max = min(self.x_min, self.x), max(self.x_max, self.x)
        self.y_min, self.y_max = min(self.y_min, self.y), max(self.y_max, self.y)
        nx, ny = self._normal(self.x, self.cx), self._normal(self.y, self.cy)
        # Some LAFVIN joystick daughterboards rotate the axes. Use the one that
        # is actually being moved; X wins ties and remains the default.
        if self.axis_mode == 1:
            self.axis, selected = 'X', nx
        elif self.axis_mode == 2:
            self.axis, selected = 'Y', ny
        elif abs(ny) > abs(nx) + 120:
            self.axis, selected = 'Y', ny
        elif abs(nx) > abs(ny) + 120:
            self.axis, selected = 'X', nx
        else:
            selected = nx if self.axis == 'X' else ny
        if abs(selected) < 125:
            selected = 0
        self.command = max(-1000, min(1000, selected * self.direction))

        if self.k1.down and self.k2.down:
            if self.combo_since is None:
                self.combo_since = now
            elif time.ticks_diff(now, self.combo_since) >= 800:
                self.combo_event = True
                self.combo_since = now + 60000
        else:
            self.combo_since = None

    def consume_combo(self):
        event = self.combo_event
        self.combo_event = False
        return event


# ------------------------------------------------------------- safety agent --
class SafetyAgent:
    def __init__(self, inputs):
        self.inputs = inputs
        self.last_step = time.ticks_ms()
        self.max_gap_ms = 0
        self.frame_faults = 0

    def step(self, now):
        gap = time.ticks_diff(now, self.last_step)
        self.last_step = now
        if gap > self.max_gap_ms:
            self.max_gap_ms = gap
        if gap > 500:
            self.frame_faults += 1
        # A physical joystick press always remains a local escape path.
        return self.inputs.sw.consume()

    @staticmethod
    def clamp(value, low, high):
        return low if value < low else high if value > high else value


# --------------------------------------------------------------- game agent --
class HumanGameAgent:
    def __init__(self):
        self.top = 55
        self.paddle_w, self.paddle_h = 108, 16
        self.player_x = self.ai_x = (W - self.paddle_w) // 2
        self.player_y, self.ai_y = H - 28, self.top + 22
        self.ball_x, self.ball_y, self.ball_size = W // 2, H // 2, 18
        self.vx, self.vy = 2, -2
        self.player_score = self.ai_score = 0

    def step(self, joystick):
        # Velocity control is robust when the ADC cannot reach rail values.
        self.player_x += (joystick * 7) // 1000
        self.player_x = SafetyAgent.clamp(self.player_x, 0, W - self.paddle_w)
        target = self.ball_x - self.paddle_w // 2
        if self.ai_x < target - 3:
            self.ai_x += 2
        elif self.ai_x > target + 3:
            self.ai_x -= 2
        self.ai_x = SafetyAgent.clamp(self.ai_x, 0, W - self.paddle_w)
        self.ball_x += self.vx
        self.ball_y += self.vy
        if self.ball_x <= 0 or self.ball_x >= W - self.ball_size:
            self.ball_x = SafetyAgent.clamp(self.ball_x, 0, W - self.ball_size)
            self.vx = -self.vx
        if (self.vy < 0 and self.ai_y <= self.ball_y <= self.ai_y + self.paddle_h
                and self.ai_x - self.ball_size <= self.ball_x <= self.ai_x + self.paddle_w):
            self.ball_y = self.ai_y + self.paddle_h
            self.vy = -self.vy
        if (self.vy > 0 and self.player_y <= self.ball_y + self.ball_size <= self.player_y + self.paddle_h
                and self.player_x - self.ball_size <= self.ball_x <= self.player_x + self.paddle_w):
            self.ball_y = self.player_y - self.ball_size
            self.vy = -self.vy
        scored = 0
        if self.ball_y < self.top:
            self.player_score += 1
            scored = 1
            self._serve(1)
        elif self.ball_y > H:
            self.ai_score += 1
            scored = -1
            self._serve(-1)
        return scored

    def _serve(self, vertical):
        self.ball_x, self.ball_y = W // 2, H // 2
        self.vx = random.choice((-2, 2))
        self.vy = 2 * vertical


# ------------------------------------------------------------ learning agent --
class LearningAgent:
    """Tiny linear Q learner: three actions, seven features, starts at zero."""
    def __init__(self):
        self.weights = [[0.0] * 7 for _ in range(3)]
        self.alpha, self.gamma, self.epsilon = 0.055, 0.94, 1.0
        self.episodes = self.hits = self.misses = 0
        self.model_x = self.opponent_x = 500
        self.ball_x = self.ball_y = 500
        self.ball_vx = random.choice((-11, -9, 9, 11))
        self.ball_vy = 12
        self.last_action = 1
        self.last_reward = 0.0

    @staticmethod
    def _features(bx, by, vx, vy, px):
        return [1.0, (bx - 500) / 500, (by - 500) / 500,
                vx / 16, vy / 16, (px - 500) / 500, (bx - px) / 500]

    @staticmethod
    def _values(weights, state):
        return [sum(weights[a][i] * state[i] for i in range(7)) for a in range(3)]

    def step(self):
        state = self._features(self.ball_x, self.ball_y, self.ball_vx,
                               self.ball_vy, self.model_x)
        q = self._values(self.weights, state)
        if random.random() < self.epsilon:
            action = random.randrange(3)
        else:
            action = 0
            if q[1] > q[action]:
                action = 1
            if q[2] > q[action]:
                action = 2
        self.last_action = action
        self.model_x += (-18, 0, 18)[action]
        self.model_x = SafetyAgent.clamp(self.model_x, 95, 905)
        if self.opponent_x < self.ball_x - 12:
            self.opponent_x += 12
        elif self.opponent_x > self.ball_x + 12:
            self.opponent_x -= 12
        self.ball_x += self.ball_vx
        self.ball_y += self.ball_vy
        if self.ball_x < 12 or self.ball_x > 988:
            self.ball_x = SafetyAgent.clamp(self.ball_x, 12, 988)
            self.ball_vx = -self.ball_vx
        reward = -0.0015 * abs(self.ball_x - self.model_x) / 500
        done = False
        if self.ball_vy < 0 and self.ball_y <= 82:
            if abs(self.ball_x - self.opponent_x) <= 125:
                self.ball_y, self.ball_vy = 82, -self.ball_vy
            else:
                reward += 0.6
                done = True
        elif self.ball_vy > 0 and self.ball_y >= 918:
            if abs(self.ball_x - self.model_x) <= 125:
                self.ball_y, self.ball_vy = 918, -self.ball_vy
                reward += 1.0
                self.hits += 1
            else:
                reward -= 1.0
                self.misses += 1
                done = True
        next_state = self._features(self.ball_x, self.ball_y, self.ball_vx,
                                    self.ball_vy, self.model_x)
        target = reward if done else reward + self.gamma * max(self._values(self.weights, next_state))
        error = target - q[action]
        for index in range(7):
            self.weights[action][index] += self.alpha * error * state[index]
        self.last_reward = reward
        if done:
            self.episodes += 1
            self.epsilon = max(0.05, self.epsilon * 0.992)
            self.model_x = self.opponent_x = 500
            self.ball_x = self.ball_y = 500
            self.ball_vx = random.choice((-12, -10, 10, 12))
            self.ball_vy = random.choice((-12, 12))


# -------------------------------------------------------------- display agent --
class DisplayAgent:
    def __init__(self, lcd):
        self.lcd = lcd

    def home(self, inputs):
        lcd = self.lcd
        lcd.fill(DARK)
        lcd.fill_rect(0, 0, W, 98, GOLD)
        lcd.text('HELLO IDO', 52, 16, BLACK, GOLD, 3)
        lcd.text('QUINCY MICRO-SWARM', 80, 60, BLACK, GOLD, 1)
        names = (('INPUT', CYAN), ('GAME', YELLOW), ('LEARN', LIME),
                 ('DISPLAY', PINK), ('SAFETY', ORANGE))
        for index, item in enumerate(names):
            y = 126 + index * 40
            lcd.fill_rect(26, y, 18, 18, item[1])
            lcd.text(item[0] + ' AGENT  ONLINE', 58, y + 5, item[1], DARK, 1)
        lcd.fill_rect(16, 348, 288, 52, rgb565(8, 38, 62))
        lcd.text('K1  HUMAN PONG', 48, 360, CYAN, rgb565(8, 38, 62), 2)
        lcd.fill_rect(16, 408, 288, 52, rgb565(12, 48, 30))
        lcd.text('K2  AI FROM ZERO', 32, 420, LIME, rgb565(12, 48, 30), 2)
        # Corner pixels prove the configured canvas really reaches 320x480.
        lcd.fill_rect(0, 476, 320, 4, GOLD)
        print('INPUT_IDLE k1=%d k2=%d sw=%d centers=%d,%d' %
              (inputs.k1.idle, inputs.k2.idle, inputs.sw.idle,
               inputs.cx, inputs.cy))

    def human_static(self):
        self.lcd.fill(BLACK)
        self.lcd.fill_rect(0, 0, W, 52, rgb565(6, 26, 45))
        self.lcd.text('K1 HUMAN', 8, 8, CYAN, rgb565(6, 26, 45), 2)
        self.lcd.text('SW=HOME', 232, 18, GREY, rgb565(6, 26, 45), 1)

    def human_frame(self, game, old):
        lcd = self.lcd
        if old is not None:
            lcd.fill_rect(old[0], game.player_y, game.paddle_w, game.paddle_h, BLACK)
            lcd.fill_rect(old[1], game.ai_y, game.paddle_w, game.paddle_h, BLACK)
            lcd.fill_rect(old[2], old[3], game.ball_size, game.ball_size, BLACK)
        lcd.fill_rect(game.player_x, game.player_y, game.paddle_w, game.paddle_h, CYAN)
        lcd.fill_rect(game.ai_x, game.ai_y, game.paddle_w, game.paddle_h, PINK)
        lcd.fill_rect(game.ball_x, game.ball_y, game.ball_size, game.ball_size, YELLOW)
        lcd.fill_rect(0, 34, W, 18, rgb565(6, 26, 45))
        lcd.text('YOU %d' % game.player_score, 8, 38, CYAN, rgb565(6, 26, 45), 1)
        lcd.text('CPU %d' % game.ai_score, 264, 38, PINK, rgb565(6, 26, 45), 1)
        return (game.player_x, game.ai_x, game.ball_x, game.ball_y)

    @staticmethod
    def _project(x, y):
        half = 86 + (72 * y) // 1000
        return (W // 2 - half + (x * half * 2) // 1000,
                100 + (y * 350) // 1000)

    def training_static(self):
        lcd = self.lcd
        lcd.fill(DARK)
        lcd.fill_rect(0, 0, W, 88, BLACK)
        lcd.text('K2 AI PONG LAB', 40, 8, LIME, BLACK, 2)
        lcd.text('REAL Q-LEARNING - ZERO WEIGHTS', 40, 38, WHITE, BLACK, 1)
        lcd.line(74, 100, 2, 450, BLUE, 3)
        lcd.line(246, 100, 317, 450, BLUE, 3)
        lcd.line(74, 100, 246, 100, BLUE, 3)
        lcd.line(2, 450, 317, 450, BLUE, 3)
        left = self._project(0, 500)
        right = self._project(1000, 500)
        lcd.line(left[0], left[1], right[0], right[1], GREY)

    def training_frame(self, learner, old, frame):
        lcd = self.lcd
        if old is not None:
            for bounds in old:
                lcd.fill_rect(bounds[0], bounds[1], bounds[2], bounds[3], DARK)

        def bounds(x, y, paddle=False):
            sx, sy = self._project(x, y)
            if paddle:
                pw, ph = 50 + (y * 70) // 1000, 8 + (y * 10) // 1000
                return sx - pw // 2, sy - ph // 2, pw, ph
            size = 9 + (y * 15) // 1000
            return sx - size // 2, sy - size // 2, size, size

        sprites = (bounds(learner.opponent_x, 70, True),
                   bounds(learner.model_x, 930, True),
                   bounds(learner.ball_x, learner.ball_y))
        lcd.fill_rect(*sprites[0], PINK)
        lcd.fill_rect(*sprites[1], LIME)
        lcd.fill_rect(*sprites[2], YELLOW)
        if frame % 10 == 0:
            lcd.fill_rect(0, 58, W, 30, BLACK)
            lcd.text('EP %d' % learner.episodes, 6, 62, CYAN, BLACK, 1)
            lcd.text('H %d' % learner.hits, 96, 62, LIME, BLACK, 1)
            lcd.text('M %d' % learner.misses, 166, 62, PINK, BLACK, 1)
            lcd.text('E %d%%' % int(learner.epsilon * 100), 238, 62, WHITE, BLACK, 1)
            lcd.fill_rect(12, 466, 296, 10, GREY)
            lcd.fill_rect(12, 466, int((1.0 - learner.epsilon) * 296), 10, LIME)
        return sprites

    def diagnostics(self, inputs, safety):
        lcd = self.lcd
        lcd.fill(BLACK)
        lcd.fill_rect(0, 0, W, 58, ORANGE)
        lcd.text('INPUT DIAGNOSTICS', 16, 16, BLACK, ORANGE, 2)
        start = time.ticks_ms()
        while True:
            now = time.ticks_ms()
            inputs.step(now)
            escape = safety.step(now)
            if inputs.k1.consume():
                inputs.direction = -inputs.direction
            if inputs.k2.consume():
                inputs.axis_mode = (inputs.axis_mode + 1) % 3
            lcd.fill_rect(0, 72, W, 350, BLACK)
            lcd.text('K1 raw %d idle %d down %d' %
                     (inputs.k1.raw, inputs.k1.idle, inputs.k1.down), 16, 82, CYAN)
            lcd.text('K2 raw %d idle %d down %d' %
                     (inputs.k2.raw, inputs.k2.idle, inputs.k2.down), 16, 112, LIME)
            lcd.text('SW raw %d idle %d down %d' %
                     (inputs.sw.raw, inputs.sw.idle, inputs.sw.down), 16, 142, ORANGE)
            lcd.text('ADC X %5d' % inputs.x, 16, 190, WHITE, BLACK, 2)
            lcd.text('ADC Y %5d' % inputs.y, 16, 224, WHITE, BLACK, 2)
            lcd.text('ACTIVE AXIS %s' % inputs.axis, 16, 272, YELLOW, BLACK, 2)
            lcd.text('COMMAND %+5d' % inputs.command, 16, 306, YELLOW, BLACK, 2)
            mode_name = ('AUTO', 'X', 'Y')[inputs.axis_mode]
            direction_name = 'NORMAL' if inputs.direction > 0 else 'FLIPPED'
            lcd.text('K1 DIR ' + direction_name, 16, 382, CYAN)
            lcd.text('K2 AXIS ' + mode_name, 176, 382, LIME)
            bar_x = 160 + (inputs.command * 140) // 1000
            lcd.fill_rect(16, 350, 288, 18, GREY)
            lcd.fill_rect(min(160, bar_x), 350, abs(bar_x - 160) + 2, 18,
                          CYAN if inputs.command < 0 else LIME)
            lcd.fill_rect(158, 344, 4, 30, WHITE)
            lcd.text('MOVE STICK / PRESS SW HOME', 48, 424, GREY)
            if escape and time.ticks_diff(now, start) > 300:
                return
            time.sleep_ms(70)


# ------------------------------------------------------------ swarm runtime --
class PicoSwarm:
    def __init__(self):
        spi = SPI(0, baudrate=40_000_000, sck=Pin(SCK),
                  mosi=Pin(MOSI), miso=Pin(MISO))
        self.lcd = LCD(spi, CS, DC, RST)
        self.inputs = InputAgent()
        self.safety = SafetyAgent(self.inputs)
        self.display = DisplayAgent(self.lcd)
        self.mode = 'HOME'

    def set_mode(self, mode):
        self.mode = mode
        rgb(0, 0, 10)
        if mode == 'HUMAN':
            self.game = HumanGameAgent()
            self.old_sprites = None
            self.display.human_static()
        elif mode == 'TRAIN':
            self.learner = LearningAgent()
            self.old_sprites = None
            self.training_frame = 0
            self.display.training_static()
            print('AI_WEIGHTS_ZERO', self.learner.weights)
        else:
            self.display.home(self.inputs)

    def run(self):
        self.set_mode('HOME')
        print('PICO_SWARM_BOOT_OK 320x480 agents=input,display,game,learning,safety')
        last_frame = time.ticks_ms()
        while True:
            now = time.ticks_ms()
            self.inputs.step(now)
            escape = self.safety.step(now)

            if self.inputs.consume_combo():
                self.display.diagnostics(self.inputs, self.safety)
                self.set_mode('HOME')
                last_frame = time.ticks_ms()
                continue

            if self.mode == 'HOME':
                # K1 and K2 are consumed only as debounced edge events.
                if self.inputs.k1.consume():
                    chirp(880)
                    self.set_mode('HUMAN')
                elif self.inputs.k2.consume():
                    chirp(660)
                    chirp(990)
                    self.set_mode('TRAIN')
            elif escape:
                self.set_mode('HOME')
            elif self.mode == 'HUMAN' and time.ticks_diff(now, last_frame) >= 42:
                # Deliberately ~24 FPS and 2px ball steps: playable, not frantic.
                score = self.game.step(self.inputs.command)
                self.old_sprites = self.display.human_frame(self.game, self.old_sprites)
                if score:
                    chirp(1100 if score > 0 else 180, 35)
                last_frame = now
            elif self.mode == 'TRAIN' and time.ticks_diff(now, last_frame) >= 32:
                self.learner.step()
                self.old_sprites = self.display.training_frame(
                    self.learner, self.old_sprites, self.training_frame)
                self.training_frame += 1
                last_frame = now

            # K1/K2 while in an activity are ignored as mode starts; SW is the
            # reliable exit. This prevents one bad/stuck key from trapping UI.
            if self.mode != 'HOME':
                self.inputs.k1.consume()
                self.inputs.k2.consume()
            time.sleep_ms(3)


try:
    PicoSwarm().run()
except Exception as error:
    _buzzer.duty_u16(0)
    rgb(40, 0, 0)
    print('PICO_SWARM_FATAL', repr(error))
    raise
