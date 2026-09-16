// board_tdeck.h — LILYGO T-Deck (ESP32-S3) pin map for ALMA-OS.
// Sources: LilyGo T-Deck schematic / official examples (utilities.h pin names).
// UNTESTED-ON-HARDWARE NOTE: verify against your board revision before flashing.
//
// לזכרה של עלמה ז"ל · ALMAWARE
#pragma once

// --- Power rail: MUST go HIGH before any peripheral (display, kb, radio, SD) ---
#define PIN_BOARD_POWERON   10

// --- Shared SPI bus (display + LoRa + SD) ---
#define PIN_SPI_SCK         40
#define PIN_SPI_MOSI        41
#define PIN_SPI_MISO        38

// --- ST7789 320x240 TFT (no reset pin — software reset only) ---
#define PIN_TFT_CS          12
#define PIN_TFT_DC          11
#define PIN_TFT_BL          42
#define TFT_WIDTH           320   // landscape
#define TFT_HEIGHT          240

// --- SX1262 LoRa ---
#define PIN_LORA_CS          9
#define PIN_LORA_DIO1       45
#define PIN_LORA_RST        17
#define PIN_LORA_BUSY       13

// --- I2C bus: keyboard (ESP32-C3 @ 0x55), touch GT911 (0x5D) ---
#define PIN_I2C_SDA         18
#define PIN_I2C_SCL          8
#define KB_I2C_ADDR       0x55
#define PIN_KB_INT          46
#define PIN_TOUCH_INT       16

// --- Trackball (pulse pins + BOOT as click) ---
#define PIN_TB_UP            3
#define PIN_TB_DOWN         15
#define PIN_TB_LEFT          1
#define PIN_TB_RIGHT         2
#define PIN_TB_CLICK         0   // shared with BOOT button

// --- Audio ---
#define PIN_I2S_BCK          7   // MAX98357A speaker
#define PIN_I2S_WS           5
#define PIN_I2S_DOUT         6
#define PIN_ES7210_MCLK     48   // ES7210 mic ADC
#define PIN_ES7210_LRCK     21
#define PIN_ES7210_SCK      47
#define PIN_ES7210_DIN      14

// --- Misc ---
#define PIN_BAT_ADC          4   // battery voltage via 1:2 divider
#define PIN_SD_CS           39

// --- ALMA-OS radio defaults (adjust to local regulations / your region) ---
#define ALMA_LORA_FREQ_MHZ   868.0f   // must match BOTH T-Decks
#define ALMA_LORA_SF         9
#define ALMA_LORA_BW_KHZ     125
#define ALMA_LORA_CR         7        // 4/7
#define ALMA_LORA_POWER_DBM  17       // conservative; SX1262 max 22
#define ALMA_LORA_SYNCWORD   0x12     // private network
