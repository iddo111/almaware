POSITION: Armed mode must be the DEFAULT to prevent the 09:46 scar from recurring; the presence gate is insufficient because it cannot distinguish the owner from a video.

REASONS:
- The 09:46 scar proves a passive presence gate fails when the owner is absent but the OS is active.
- The ArmSwitch is the only mechanism that explicitly requires a deliberate user action (Ctrl+Alt+A) to authorize typing.
- Disarmed speech parking prevents accidental data leakage while the user is away.

RISKS:
- The user may forget to re-arm after 15 minutes, causing a brief idle period where the mic is silent.
- The user may find the hotkey frictional, leading to accidental disarming during normal dictation.

RECOMMENDED DEFAULTS:
- enter_idle_limit_s: 600 (Fail-closed)
- type_idle_limit_s: 120 (Fail-open)
- arm_timeout_s: 900