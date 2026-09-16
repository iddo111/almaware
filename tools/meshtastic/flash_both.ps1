Set-Location 'D:\CLAUDE\tools\meshtastic\fw-s3'
$fw = 'firmware-heltec-v4-2.7.22.96dd647.factory.bin'
$lfs = 'littlefs-heltec-v4-2.7.22.96dd647.bin'
$ota = 'mt-esp32s3-ota.bin'

# Read offsets from mt.json
$meta = Get-Content 'firmware-heltec-v4-2.7.22.96dd647.mt.json' | ConvertFrom-Json
$ota_offset  = ($meta.part | Where-Object subtype -eq 'ota_1').offset
$spiffs_offset = ($meta.part | Where-Object subtype -eq 'spiffs').offset
Write-Host "OTA offset: $ota_offset  SPIFFS offset: $spiffs_offset"

foreach ($port in @('COM3','COM4')) {
    Write-Host "`n=== Flashing $port ===" -ForegroundColor Cyan
    python -m esptool --port $port --baud 921600 erase_flash
    python -m esptool --port $port --baud 921600 write_flash 0x00 $fw
    python -m esptool --port $port --baud 921600 write_flash $ota_offset $ota
    python -m esptool --port $port --baud 921600 write_flash $spiffs_offset $lfs
    Write-Host "=== $port done ===" -ForegroundColor Green
}
