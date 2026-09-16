# EMDR Widget — Restyle Plan

**Current state:** Floating tray-based PyQt6 widget. Default Qt Fusion look, grey buttons, system-ish fonts. Functional but visually dated.

**Effort:** Small (done tonight).

## Applied tonight
- `emdr_widget.py::main()` now calls `apply_theme(app, mode="dark")` from `D:\NEWCLAUDE\DESIGN_SYSTEM`.
- Dark mode chosen because EMDR is a floating overlay — dark surfaces blend with the user's focus context (videos, therapy sessions) without glare.

## Tokens adopted
- `color.brand.primary` #4F46E5 (indigo) → Start/Stop buttons
- `color.dark.bg` #0B0B0F → main popover background
- `radius.md` 10px → buttons, inputs
- `font.primary` Heebo/Inter → labels, controls
- Slider: indigo track + white-with-indigo-border handle (therapy feel)

## Next passes (medium effort)
- Replace the circular "start" button icon with curated Lucide `play` / `pause` SVG from `DESIGN_SYSTEM/icons/`.
- Add objectName="h2" on the title label so QSS typography tier applies.
- Add `.accent` class to the "Test pan" button (amber, secondary CTA).
- Custom speed-slider tick marks in muted tone.

## Do NOT touch
- Audio code (one_audio rule).
- `raise_()` / `activateWindow()` — focus-theft red line.
