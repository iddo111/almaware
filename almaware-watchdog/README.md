# ALMAWARE monitoring

The current local status surface is:

- `almaware-cockpit/index.html` - browser dashboard;
- `almaware-hud/collector.py` - read-only collector and `status.json` writer;
- `almaware-hud/hud.py` - optional always-on-top desktop widget;
- `almaware-cleanroom/` - policy-first assistant core (library/tests, not a live connector).

`ensure-almaware-suite.ps1` is a legacy multi-service watchdog. It is intentionally
not installed by the core monitor because its registry includes unrelated local
dashboards and Quorum.

## Safe health check

```powershell
pwsh -NoProfile -File .\check-almaware-core.ps1 -Json
```

The check is local-only and read-only. To start the collector when (and only when)
no collector process is alive:

```powershell
pwsh -NoProfile -File .\check-almaware-core.ps1 -Repair -WriteLog -Json
```

A live process with stale output is never killed or restarted automatically; the
monitor reports `manual_check_required` instead. This avoids duplicate writers and
protects any in-flight diagnostics.

`install-core-monitor-task.ps1` prefers a two-minute scheduled check. If Windows
denies user Task Scheduler registration, it installs a current-user logon entry
that runs the same check in singleton-protected loop mode. Neither mode manages
DGX nodes, models, Quorum, microphones, connectors, or websites.
