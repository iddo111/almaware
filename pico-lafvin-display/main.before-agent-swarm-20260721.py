# ============================================================================
#  LAFVIN Pico Dev Kit  ·  "HELLO IDO" + PONG        ALMAWARE / Diyalna
#  Display driven with LAFVIN's ST7796U init sequence,
#  full 320x480 portrait, SPI0, INVON. RGB WS2812 GP12 · Buzzer GP13
#  Buttons K1=GP15 K2=GP14 (active-HIGH on Pico W) · Joystick X=GP26 Y=GP27
#  MicroPython (RPI_PICO).            לזכרה של עלמה ז"ל · iddoperez.ai
# ============================================================================
from machine import Pin, SPI, ADC, PWM
import framebuf, time, rp2, random

SCK, MOSI, MISO = 2, 3, 4
CS, DC, RST     = 5, 6, 7
BUZZER, RGB_PIN = 13, 12
K1_PIN, K2_PIN  = 15, 14
JOY_SW, ADC_X, ADC_Y = 22, 26, 27
W, H = 320, 480

def rgb565(r, g, b): return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
BLACK=0x0000; WHITE=0xFFFF; GREEN=0x07E0; CYAN=0x07FF; YELLOW=0xFFE0
GOLD=rgb565(212,160,23); BLUE=rgb565(80,140,255); PINK=rgb565(255,90,140); GREY=rgb565(60,66,90)
NAVY=rgb565(3,12,28); LIME=rgb565(90,255,130); ORANGE=rgb565(255,145,40)

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
        s._c(0x2A, b'\x00\x00\x01\x3F')   # CASET 0..319
        s._c(0x2B, b'\x00\x00\x01\xDF')   # RASET 0..479
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
        # MicroPython 1.28 no longer accepts bytearray * int on this build.
        # Build the RGB565 scanline explicitly so every fill operation works.
        row=bytearray(w*2)
        hi=col>>8; lo=col&0xFF
        for i in range(0, len(row), 2):
            row[i]=hi; row[i+1]=lo
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
    def line(s, x0, y0, x1, y1, col, thickness=1):
        dx=abs(x1-x0); sx=1 if x0<x1 else -1
        dy=-abs(y1-y0); sy=1 if y0<y1 else -1
        err=dx+dy
        while True:
            s.fill_rect(x0, y0, thickness, thickness, col)
            if x0==x1 and y0==y1: break
            e2=err*2
            if e2>=dy: err+=dy; x0+=sx
            if e2<=dx: err+=dx; y0+=sy

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

def adc_average(adc, samples=24):
    total=0
    for _ in range(samples):
        total+=adc.read_u16(); time.sleep_ms(2)
    return total//samples

# Calibrate the resting point instead of assuming a perfect 32768 center.
JOY_CX=adc_average(jx); JOY_CY=adc_average(jy)

def joystick_x(maximum):
    # LAFVIN's reference firmware maps GP26 directly across the X range.
    return (jx.read_u16()*maximum)//65535

def pressed(pin):
    return pin.value()==1

def wait_release(pin):
    while pressed(pin): time.sleep_ms(20)

spi=SPI(0, baudrate=40_000_000, sck=Pin(SCK), mosi=Pin(MOSI), miso=Pin(MISO))
lcd=LCD(spi, CS, DC, RST)

# ---------------------------------------------------------------- boot --------
def boot_screen():
    lcd.fill(BLACK)
    lcd.fill_rect(0, 0, W, 90, GOLD)
    lcd.text("HELLO", 100, 12, BLACK, GOLD, 3)
    lcd.text("IDO!", 112, 50, BLACK, GOLD, 3)
    lcd.text("ALMAWARE  DIYALNA", 88, 116, GOLD, BLACK, 1)
    lcd.text("crossbar brain", 104, 136, GREY, BLACK, 1)
    for r in range(3):
        for c in range(3):
            lcd.fill_rect(97+c*48, 180+r*54, 30, 30, GREY)
            lcd.fill_rect(107+c*48, 190+r*54, 10, 10, GOLD)
    lcd.text("K1  HUMAN PONG", 48, 392, CYAN, BLACK, 2)
    lcd.text("K2  AI TRAIN 3D", 32, 430, LIME, BLACK, 2)
    for (f, c) in ((523,(40,0,0)),(659,(0,40,0)),(784,(0,0,40)),(1047,(40,40,0))):
        rgb(*c); tone(f, 150)
    rgb(0, 0, 8)

# ----------------------------------------------------------- K1 HUMAN PONG ---
def human_pong():
    TOP=48
    lcd.fill(BLACK)
    lcd.fill_rect(0, TOP, W, 2, GREY)
    pw, ph = 104, 16
    px=(W-pw)//2; ax=(W-pw)//2
    py=H-26; ay=TOP+30
    bx, by = W//2, H//2; bs=18
    vx, vy = 2, -2
    ps=0; as_=0
    opx=px; oax=ax; obx=bx; oby=by
    def paddle(x, y, ox, col):
        if x!=ox: lcd.fill_rect(ox, y, pw, ph, BLACK)
        lcd.fill_rect(x, y, pw, ph, col)
    def score():
        lcd.fill_rect(0, 0, W, 42, BLACK)
        lcd.text("YOU %d" % ps, 8, 10, CYAN, BLACK, 2)
        lcd.text("CPU %d" % as_, W-104, 10, PINK, BLACK, 2)
    score(); paddle(px, py, px, CYAN); paddle(ax, ay, ax, PINK)
    while True:
        px=joystick_x(W-pw)
        if ax+pw//2 < bx-2: ax+=2
        elif ax+pw//2 > bx+2: ax-=2
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
            ps+=1; score(); tone(1200,120); rgb(0,40,0); bx,by=W//2,H//2; vx,vy=2,2
        if by>H-bs:
            as_+=1; score(); tone(160,200); rgb(40,0,0); bx,by=W//2,H//2; vx,vy=-2,-2
        paddle(px, py, opx, CYAN); opx=px
        paddle(ax, ay, oax, PINK); oax=ax
        if bx!=obx or by!=oby: lcd.fill_rect(obx, oby, bs, bs, BLACK)
        lcd.fill_rect(bx, by, bs, bs, YELLOW); obx, oby=bx, by
        if pressed(k2):
            wait_release(k2); return
        time.sleep_ms(34)

# -------------------------------------------------------- K2 AI TRAINING 3D ---
def ai_train_pong_3d():
    court_top=88; court_bottom=462

    def project(x, y):
        half=86+(72*y)//1000
        sx=W//2-half+(x*(half*2))//1000
        sy=court_top+(y*(court_bottom-court_top))//1000
        return sx,sy

    def court():
        lcd.fill(NAVY)
        lcd.fill_rect(0,0,W,78,BLACK)
        lcd.text("AI PONG LAB", 64,8,LIME,BLACK,2)
        lcd.text("LEARNING LIVE FROM ZERO", 68,38,WHITE,BLACK,1)
        lcd.line(74,court_top,2,court_bottom,BLUE,3)
        lcd.line(246,court_top,317,court_bottom,BLUE,3)
        lcd.line(74,court_top,246,court_top,BLUE,3)
        lcd.line(2,court_bottom,317,court_bottom,BLUE,3)
        mlx,mly=project(0,500); mrx,mry=project(1000,500)
        lcd.line(mlx,mly,mrx,mry,GREY,1)

    def sprite_bounds(x, y, paddle=False):
        sx,sy=project(x,y)
        if paddle:
            pw=50+(y*70)//1000; ph=8+(y*10)//1000
            return sx-pw//2,sy-ph//2,pw,ph
        size=9+(y*15)//1000
        return sx-size//2,sy-size//2,size,size

    def draw_sprite(bounds, color):
        lcd.fill_rect(bounds[0],bounds[1],bounds[2],bounds[3],color)

    def features(bx,by,vx,vy,px):
        return [1.0,(bx-500)/500,(by-500)/500,vx/16,vy/16,
                (px-500)/500,(bx-px)/500]

    weights=[[0.0]*7 for _ in range(3)]
    alpha=0.055; gamma=0.94; epsilon=1.0
    episodes=0; hits=0; misses=0; frame=0
    model_x=500; opponent_x=500
    ball_x=500; ball_y=500
    ball_vx=random.choice((-11,-9,9,11)); ball_vy=12
    old_ball=sprite_bounds(ball_x,ball_y)
    old_model=sprite_bounds(model_x,930,True)
    old_opp=sprite_bounds(opponent_x,70,True)
    court()

    while True:
        for _ in range(1):
            state=features(ball_x,ball_y,ball_vx,ball_vy,model_x)
            q=[sum(weights[a][i]*state[i] for i in range(7)) for a in range(3)]
            if random.random()<epsilon: action=random.randrange(3)
            else: action=max(range(3),key=lambda a:q[a])
            model_x+=(-18,0,18)[action]
            if model_x<95: model_x=95
            if model_x>905: model_x=905

            if opponent_x<ball_x-12: opponent_x+=12
            elif opponent_x>ball_x+12: opponent_x-=12
            ball_x+=ball_vx; ball_y+=ball_vy
            if ball_x<12: ball_x=12; ball_vx=-ball_vx
            if ball_x>988: ball_x=988; ball_vx=-ball_vx

            reward=-0.0015*abs(ball_x-model_x)/500
            done=False
            if ball_vy<0 and ball_y<=82:
                if abs(ball_x-opponent_x)<=125:
                    ball_y=82; ball_vy=-ball_vy
                else:
                    reward+=0.6; done=True
            elif ball_vy>0 and ball_y>=918:
                if abs(ball_x-model_x)<=125:
                    ball_y=918; ball_vy=-ball_vy; reward+=1.0; hits+=1
                else:
                    reward-=1.0; misses+=1; done=True

            next_state=features(ball_x,ball_y,ball_vx,ball_vy,model_x)
            next_q=[sum(weights[a][i]*next_state[i] for i in range(7)) for a in range(3)]
            target=reward if done else reward+gamma*max(next_q)
            error=target-q[action]
            for i in range(7): weights[action][i]+=alpha*error*state[i]

            if done:
                episodes+=1; epsilon=max(0.05,epsilon*0.992)
                ball_x=500; ball_y=500
                ball_vx=random.choice((-12,-10,10,12)); ball_vy=random.choice((-12,12))
                model_x=500; opponent_x=500

        draw_sprite(old_ball,NAVY); draw_sprite(old_model,NAVY); draw_sprite(old_opp,NAVY)
        new_opp=sprite_bounds(opponent_x,70,True)
        new_model=sprite_bounds(model_x,930,True)
        new_ball=sprite_bounds(ball_x,ball_y)
        draw_sprite(new_opp,PINK); draw_sprite(new_model,LIME); draw_sprite(new_ball,YELLOW)
        old_ball=new_ball; old_model=new_model; old_opp=new_opp

        if frame%12==0:
            lcd.fill_rect(0,58,W,26,BLACK)
            lcd.text("EP %d"%episodes,8,64,CYAN,BLACK,1)
            lcd.text("HIT %d"%hits,104,64,LIME,BLACK,1)
            lcd.text("MISS %d"%misses,200,64,PINK,BLACK,1)
            lcd.fill_rect(12,470,296,8,GREY)
            learned=int((1.0-epsilon)*296)
            lcd.fill_rect(12,470,learned,8,LIME)
        if frame%90==0:
            court()
        frame+=1
        if pressed(k2) or pressed(k1):
            if pressed(k2): wait_release(k2)
            if pressed(k1): wait_release(k1)
            return
        time.sleep_ms(30)

# ---------------------------------------------------------------- main --------
boot_screen()
print("LAFVIN_DISPLAY_BOOT_OK")
while True:
    if pressed(k1):
        wait_release(k1); tone(880,80); human_pong(); boot_screen()
    elif pressed(k2):
        wait_release(k2); tone(660,80); tone(990,80); ai_train_pong_3d(); boot_screen()
    elif sw.value()==1:
        tone(880,80); human_pong(); boot_screen()
    time.sleep_ms(40)
