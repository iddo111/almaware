# firmware/ — ALMA-OS v0.2 scaffold (target module layout)

This tree is the **blueprint**, not the buildable firmware. The buildable
v0.1 skeleton (flash it with `pio run -t upload`) is in `../src/` and
`../platformio.ini` — untouched by this scaffold.

Read `../design/04-firmware-os.md` first — it explains the FreeRTOS task
split, the event bus, the RTL text-shaping algorithm, why LVGL is rejected,
storage layout, and power management that this tree's headers implement the
shape of.

Every header here is a **stub**: signatures + comments, no `.cpp` bodies,
not referenced by `platformio.ini`. They exist so implementation work has a
fixed contract to fill in module-by-module, migrating logic out of `src/`
incrementally (e.g. `src/mesh.h` moves to `firmware/mesh/mesh.h` unchanged,
`src/display_st7789.cpp`'s inline RTL shaping gets factored into
`firmware/text/bidi_rtl.h`) while `src/` keeps compiling and flashing at
every step.

Do not add these directories to `platformio.ini`'s `src_dir`/`lib_dir` until
a module is actually filled in and verified to compile — an empty scaffold
should never break the v0.1 build.

לזכרה של עלמה ז"ל · ALMAWARE
