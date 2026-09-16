# ============================================================================
#  LAFVIN Pico Dev Kit  ·  "HELLO IDO" + PONG        ALMAWARE / Diyalna
#  Display driven EXACTLY as LAFVIN's firmware does: ILI9341-style init,
#  240x320 portrait, SPI0, INVON. RGB WS2812 GP12 · Buzzer GP13
#  Buttons K1=GP15 K2=GP14 (active-HIGH) · Joystick X=GP26 Y=GP27 SW=GP22
#  MicroPython (RPI_PICO).            לזכרה של עלמה ז"ל · iddoperez.ai
# ============================================================================
from machine import Pin, SPI, ADC, PWM
import framebuf, time, rp2

SCK, MOSI, MISO = 2, 3, 4
CS, DC, RST     = 5, 6, 7
BUZZER, RGB_PIN = 13, 12
K1_PIN, K2_PIN  = 15, 14
JOY_SW, ADC_X, ADC_Y = 22, 26, 27
W, H = 240, 320                       # real resolution (from LAFVIN CASET/RASET)

def rgb565(r, g, b): return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
BLACK=0x0000; WHITE=0xFFFF; GREEN=0x07E0; CYAN=0x07FF; YELLOW=0xFFE0
GOLD=rgb565(212,160,23); BLUE=rgb565(80,140,255); PINK=rgb565(255,90,140); GREY=rgb565(60,66,90)

# ---------------------------------------------------------------- LCD ---------
class LCD:
    def __init__(s, spi, cs, dc, rst):
        s.spi=spi; s.cs=Pin(cs,Pin.OUT,value=1); s.dc=Pin(dc,Pin.OUT,value=0)
        s.rst=Pin(rst,Pin.OUT,value=1); s.w=W; s.h=H
        s._reset(); s._init()
    def _c(s, c, d=None):
        s.cs(0); s.dc(0); s.spi.write(bytes([c]))
        if d is not None: s.dc(1); s.spi.write(d)
        s.cs(1)
    def _reset(s):
        s.rst(1); time.sleep_ms(20); s.rst(0); time.sleep_ms(40); s.rst(1); time.sleep_ms(120)
    def _init(s):
        # EXACT LAFVIN init sequence (ILI9341-style power-on for this panel)
        s._c(0xCF, b'\x00\x83\x30')
        s._c(0xED, b'\x64\x03\x12\x81')
        s._c(0xE8, b'\x85\x01\x79')
        s._c(0xCB, b'\x39\x2C\x00\x34\x02')
        s._c(0xF7, b'\x20')
        s._c(0xEA, b'\x00\x00')
        s._c(0xC0, b'\x26')            # Power Control 1
        s._c(0xC1, b'\x11')            # Power Control 2
        s._c(0xC5, b'\x35\x3E')        # VCOM Control 1
        s._c(0xC7, b'\xBE')            # VCOM Control 2
        s._c(0x36, b'\x28')
        s._c(0x3A, b'\x05')            # COLMOD RGB565
        s._c(0xB1, b'\x00\x1B')        # frame rate
        s._c(0xF2, b'\x08')
        s._c(0x26, b'\x01')
        s._c(0xE0, b'\x1F\x1A\x18\x0A\x0F\x06\x45\x87\x32\x0A\x07\x02\x07\x05\x00')  # +gamma
        s._c(0xE1, b'\x00\x25\x27\x05\x10\x09\x3A\x78\x4D\x05\x18\x0D\x38\x3A\x1F')  # -gamma
        s._c(0x2A, b'\x00\x00\x00\xEF')   # CASET 0..239
        s._c(0x2B, b'\x00\x00\x01\x3F')   # RASET 0..319
        s._c(0x2C)
        s._c(0xB7, b'\x07')
        s._c(0xB6, b'\x0A\x82\x27\x00')
        s._c(0x11); time.sleep_ms(120)    # SLPOUT
        s._c(0x29); time.sleep_ms(120)    # DISPON
        s._c(0x36, b'\x48')               # MADCTL portrait (LAFVIN set_orientation PORTRAIT)
        s._c(0x21)                        # INVON
    def _win(s, x0, y0, x1, y1):
        s._c(0x2A, bytes([x0>>8, x0&0xFF, x1>>8, x1&0xFF]))
        s._c(0x2B, bytes([y0>>8, y0&0xFF, y1>>8, y1&0xFF]))
        s._c(0x2C)
    def fill_rect(s, x, y, w, h, col):
        if w<=0 or h<=0: return
        if x<0: w+=x; x=0
        if y<0: h+=y; y=0
        if x+w>s.w: w=s.w-x
        if y+h>s.h: h=s.h-y
        if w<=0 or h<=0: return
        s._win(x, y, x+w-1, y+h-1)
        row=bytearray([col>>8, col&0xFF])*w
        s.cs(0); s.dc(1)
        for _ in range(h): s.spi.write(row)
        s.cs(1)
    def fill(s, col): s.fill_rect(0, 0, s.w, s.h, col)
    def _blit(s, buf, x, y, w, h):
        s._win(x, y, x+w-1, y+h-1); s.cs(0); s.dc(1); s.spi.write(buf); s.cs(1)
    def text(s, txt, x, y, fg=WHITE, bg=BLACK, scale=1):
        tw=len(txt)*8
        buf=bytearray(tw*8*2)
        fb=framebuf.FrameBuffer(buf, tw, 8, framebuf.RGB565)
        fb.fill(bg); fb.text(txt, 0, 0, fg)
        if scale==1:
            s._blit(buf, x, y, tw, 8); return
        for ry in range(8):
            line=bytearray(tw*scale*2)
            for rx in range(tw):
                o0=(ry*tw+rx)*2; b0=buf[o0]; b1=buf[o0+1]
                for k in range(scale):
                    o=(rx*scale+k)*2; line[o]=b0; line[o+1]=b1
            s._win(x, y+ry*scale, x+tw*scale-1, y+ry*scale+scale-1)
            s.cs(0); s.dc(1)
            for _ in range(scale): s.spi.write(line)
            s.cs(1)

# ---------------------------------------------------------------- WS2812 -----
@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW, out_shiftdir=rp2.PIO.SHIFT_LEFT,
             autopull=True, pull_thresh=24)
def _ws():
    label("bitloop"); out(x, 1).side(0)[2]; jmp(not_x, "do0").side(1)[1]
    jmp("bitloop").side(1)[4]
    label("do0"); nop().side(0)[4]
_sm=rp2.StateMachine(0, _ws, freq=8_000_000, sideset_base=Pin(RGB_PIN)); _sm.active(1)
def rgb(r, g, b): _sm.put((g<<16)|(r<<8)|b, 8)

# ---------------------------------------------------------------- buzzer -----
_buz=PWM(Pin(BUZZER)); _buz.duty_u16(0)
def tone(f, ms, duty=9000):
    if f>0: _buz.freq(f); _buz.duty_u16(duty)
    time.sleep_ms(ms); _buz.duty_u16(0)

# ---------------------------------------------------------------- inputs -----
jx=ADC(Pin(ADC_X)); jy=ADC(Pin(ADC_Y))
sw=Pin(JOY_SW, Pin.IN, Pin.PULL_DOWN)
k1=Pin(K1_PIN, Pin.IN, Pin.PULL_DOWN); k2=Pin(K2_PIN, Pin.IN, Pin.PULL_DOWN)

spi=SPI(0, baudrate=40_000_000, sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
lcd=LCD(spi, CS, DC, RST)

# ---------------------------------------------------------------- boot --------
def boot_screen():
    lcd.fill(BLACK)
    lcd.fill_rect(0, 0, W, 66, GOLD)
    lcd.text("HELLO", 60, 9, BLACK, GOLD, 3)     # 120px wide -> centered
    lcd.text("IDO!", 72, 37, BLACK, GOLD, 3)     # 96px wide  -> centered
    lcd.text("ALMAWARE  DIYALNA", 52, 86, GOLD, BLACK, 1)
    lcd.text("crossbar brain", 64, 102, GREY, BLACK, 1)
    for r in range(3):
        for c in range(3):
            lcd.fill_rect(58+c*46, 130+r*44, 30, 30, GREY)
            lcd.fill_rect(68+c*46, 140+r*44, 10, 10, GOLD)
    lcd.text("K1 - PONG", 48, 285, CYAN, BLACK, 2)
    for (f, c) in ((523,(40,0,0)),(659,(0,40,0)),(784,(0,0,40)),(1047,(40,40,0))):
        rgb(*c); tone(f, 150)
    rgb(0, 0, 8)

# ---------------------------------------------------------------- PONG --------
def pong():
    TOP=72
    lcd.fill_rect(0, TOP, W, H-TOP, BLACK)
    lcd.fill_rect(0, TOP, W, 2, GREY)
    pw, ph = 50, 10
    px=(W-pw)//2; ax=(W-pw)//2
    py=H-24; ay=TOP+12
    bx, by = W//2, H//2; bs=9
    vx, vy = 3, -4
    ps=0; as_=0
    opx=px; oax=ax; obx=bx; oby=by
    def paddle(x, y, ox, col):
        if x!=ox: lcd.fill_rect(ox, y, pw, ph, BLACK)
        lcd.fill_rect(x, y, pw, ph, col)
    def score():
        lcd.fill_rect(0, TOP+6, W, 16, BLACK)
        lcd.text("YOU %d" % ps, 10, TOP+8, CYAN, BLACK, 1)
        lcd.text("CPU %d" % as_, 170, TOP+8, PINK, BLACK, 1)
    score(); paddle(px, py, px, CYAN); paddle(ax, ay, ax, PINK)
    while True:
        px=int(jx.read_u16()*(W-pw)/65535)
        if px<0: px=0
        if px>W-pw: px=W-pw
        if ax+pw//2 < bx-3: ax+=3
        elif ax+pw//2 > bx+3: ax-=3
        if ax<0: ax=0
        if ax>W-pw: ax=W-pw
        bx+=vx; by+=vy
        if bx<=0: bx=0; vx=-vx; tone(400,8)
        if bx>=W-bs: bx=W-bs; vx=-vx; tone(400,8)
        if vy<0 and ay+ph>=by>=ay and ax-bs<=bx<=ax+pw:
            vy=-vy; by=ay+ph; tone(700,10)
        if vy>0 and py<=by+bs<=py+ph and px-bs<=bx<=px+pw:
            vy=-vy; by=py-bs; tone(900,10); rgb(0,30,0)
        if by<TOP+2:
            ps+=1; score(); tone(1200,120); rgb(0,40,0); bx,by=W//2,H//2; vx,vy=3,4
        if by>H-bs:
            as_+=1; score(); tone(160,200); rgb(40,0,0); bx,by=W//2,H//2; vx,vy=-3,-4
        paddle(px, py, opx, CYAN); opx=px
        paddle(ax, ay, oax, PINK); oax=ax
        if bx!=obx or by!=oby: lcd.fill_rect(obx, oby, bs, bs, BLACK)
        lcd.fill_rect(bx, by, bs, bs, YELLOW); obx, oby=bx, by
        if k2.value()==1: return
        time.sleep_ms(16)

# ---------------------------------------------------------------- main --------
boot_screen()
while True:
    if k1.value()==1 or sw.value()==1:
        tone(880, 80); pong(); boot_screen()
    time.sleep_ms(40)
