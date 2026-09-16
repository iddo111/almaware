# XIAO RP2350 compile-only bring-up

This minimal sketch proves that the Windows Arduino toolchain can compile for
the connected Seeed XIAO RP2350. It deliberately performs no GPIO writes and
has not been uploaded to the board.

Target FQBN:

`rp2040:rp2040:seeed_xiao_rp2350`

Compile:

```powershell
& 'C:\Program Files\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe' `
  compile --fqbn rp2040:rp2040:seeed_xiao_rp2350 `
  D:\CLAUDE\xiao-rp2350-bringup
```

Uploading is intentionally a separate decision because it replaces the
firmware currently on COM17.
