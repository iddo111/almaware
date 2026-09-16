**POSITION:** Ship a dual‑check that first attempts a read‑only `OpenMutexW` on **Global\ALMAWARE_KESHEV_SINGLE** and, only if the mutex is absent, validates the **state\events.jsonl** heartbeat (younger than 90 s); abort start when either test signals KESHEV A is alive.

**REASONS:**  
- **(a) OpenMutexW read‑only** is atomic, zero‑impact, and directly reflects A’s process lifetime via the kernel‑owned mutex.  
- **(c) Journal freshness** is a reliable secondary signal that survives brief mutex‑release windows (e.g., A crashes after releasing the mutex but before exiting).  
- Both mechanisms are inexpensive, avoid any device‑open or process‑list enumeration, and respect the “no‑disturb” constraint.

**RISKS:**  
- A rare race where A releases the mutex but the journal is still fresh, causing a false‑positive block (acceptable – better to miss a start than corrupt dictation).  
- If the journal file is corrupted or inaccessible, the interlock may miss A’s presence (mitigated by fallback to the mutex check).