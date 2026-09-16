#include <Arduino.h>
#include <IRac.h>
#include <IRremoteESP8266.h>
#include <M5Cardputer.h>

namespace {

constexpr uint16_t kIrTxPin = 44;
constexpr uint8_t kMinTemp = 16;
constexpr uint8_t kMaxTemp = 30;

struct ProtocolChoice {
    decode_type_t type;
    const char* name;
};

constexpr ProtocolChoice kProtocols[] = {
    {decode_type_t::GREE, "GREE"},
    {decode_type_t::MIDEA, "MIDEA"},
    {decode_type_t::ELECTRA_AC, "ELECTRA"},
};

constexpr stdAc::opmode_t kModes[] = {
    stdAc::opmode_t::kCool,
    stdAc::opmode_t::kHeat,
    stdAc::opmode_t::kDry,
    stdAc::opmode_t::kFan,
    stdAc::opmode_t::kAuto,
};

constexpr const char* kModeNames[] = {"COOL", "HEAT", "DRY", "FAN", "AUTO"};

constexpr stdAc::fanspeed_t kFans[] = {
    stdAc::fanspeed_t::kAuto,
    stdAc::fanspeed_t::kLow,
    stdAc::fanspeed_t::kMedium,
    stdAc::fanspeed_t::kHigh,
};

constexpr const char* kFanNames[] = {"AUTO", "LOW", "MED", "HIGH"};

IRac ac(kIrTxPin);
size_t protocolIndex = 0;
size_t modeIndex = 0;
size_t fanIndex = 0;
uint8_t temperature = 24;
bool power = false;
bool swing = false;
String statusLine = "READY - press ENTER to send";

void drawUi() {
    auto& display = M5Cardputer.Display;
    display.fillScreen(TFT_WHITE);
    display.setTextColor(TFT_BLACK, TFT_WHITE);
    display.setFont(&fonts::Font0);
    display.setTextSize(2);
    display.setCursor(8, 7);
    display.printf("TADIRAN IR  %s", power ? "ON" : "OFF");

    display.setTextSize(1);
    display.setCursor(8, 32);
    display.printf("Protocol: %s", kProtocols[protocolIndex].name);
    display.setCursor(8, 48);
    display.printf("Mode: %-4s  Temp: %u C", kModeNames[modeIndex], temperature);
    display.setCursor(8, 64);
    display.printf("Fan: %-4s  Swing: %s", kFanNames[fanIndex], swing ? "ON" : "OFF");

    display.drawFastHLine(8, 82, display.width() - 16, TFT_DARKGREY);
    display.setCursor(8, 90);
    display.print("P power  +/- temp  M mode");
    display.setCursor(8, 104);
    display.print("F fan  S swing  R protocol");

    display.setTextColor(TFT_BLUE, TFT_WHITE);
    display.setCursor(8, 121);
    display.print(statusLine);
}

void applyState() {
    ac.next.protocol = kProtocols[protocolIndex].type;
    ac.next.model = 1;
    ac.next.power = power;
    ac.next.mode = kModes[modeIndex];
    ac.next.celsius = true;
    ac.next.degrees = temperature;
    ac.next.fanspeed = kFans[fanIndex];
    ac.next.swingv = swing ? stdAc::swingv_t::kAuto : stdAc::swingv_t::kOff;
    ac.next.swingh = stdAc::swingh_t::kOff;
    ac.next.quiet = false;
    ac.next.turbo = false;
    ac.next.econo = false;
    ac.next.light = false;
    ac.next.filter = false;
    ac.next.clean = false;
    ac.next.beep = false;
    ac.next.sleep = -1;
    ac.next.clock = -1;
}

void sendState() {
    applyState();
    statusLine = ac.sendAc() ? "SENT - point IR at the AC" : "SEND FAILED / unsupported";
    Serial.printf("IR %s: protocol=%s power=%d mode=%s temp=%u fan=%s swing=%d\n",
                  statusLine.c_str(), kProtocols[protocolIndex].name, power,
                  kModeNames[modeIndex], temperature, kFanNames[fanIndex], swing);
    drawUi();
}

void handleCharacter(char key) {
    switch (key) {
        case 'p':
        case 'P':
            power = !power;
            statusLine = "CHANGED - press ENTER to send";
            break;
        case '+':
        case '=':
            if (temperature < kMaxTemp) ++temperature;
            statusLine = "CHANGED - press ENTER to send";
            break;
        case '-':
        case '_':
            if (temperature > kMinTemp) --temperature;
            statusLine = "CHANGED - press ENTER to send";
            break;
        case 'm':
        case 'M':
            modeIndex = (modeIndex + 1) % (sizeof(kModes) / sizeof(kModes[0]));
            statusLine = "CHANGED - press ENTER to send";
            break;
        case 'f':
        case 'F':
            fanIndex = (fanIndex + 1) % (sizeof(kFans) / sizeof(kFans[0]));
            statusLine = "CHANGED - press ENTER to send";
            break;
        case 's':
        case 'S':
            swing = !swing;
            statusLine = "CHANGED - press ENTER to send";
            break;
        case 'r':
        case 'R':
            protocolIndex =
                (protocolIndex + 1) % (sizeof(kProtocols) / sizeof(kProtocols[0]));
            statusLine = "PROTOCOL CHANGED - test carefully";
            break;
        default:
            return;
    }
    drawUi();
}

}  // namespace

void setup() {
    Serial.begin(115200);
    auto cfg = M5.config();
    M5Cardputer.begin(cfg, true);
    M5Cardputer.Display.setRotation(1);
    drawUi();
}

void loop() {
    M5Cardputer.update();
    if (!M5Cardputer.Keyboard.isChange() || !M5Cardputer.Keyboard.isPressed()) {
        delay(10);
        return;
    }

    auto& keys = M5Cardputer.Keyboard.keysState();
    if (keys.enter) sendState();
    for (char key : keys.word) handleCharacter(key);
    delay(30);
}
