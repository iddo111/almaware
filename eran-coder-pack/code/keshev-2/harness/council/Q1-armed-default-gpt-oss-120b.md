**POSITION:** The default should be presence‑gate‑only, with armed mode offered as an opt‑in for high‑risk contexts.  

**REASONS:**  
- Real‑world measurements show the presence gate already blocks Enter after 120 s and stops all typing after 600 s, preventing the 09:46 “scar” without extra steps.  
- Requiring the Ctrl + Alt + A hotkey for every session adds the friction the owner hates and raises the chance of forgetting to arm, which would increase false‑negatives.  
- When extra safety is needed (e.g., meetings, recordings), arm‑mode’s 15‑minute timeout gives a short, explicit protection window while still allowing hands‑free dictation.  

**RISKS (accepted):**  
- In long idle periods (>10 min) the mic may still type silently, potentially leaking content if the user steps away unnoticed.  
- Users might neglect to enable arm‑mode in truly sensitive environments, relying solely on the weaker presence gate.  

**Recommended defaults:** `enter_idle_limit_s = 120`, `type_idle_limit_s = 600`, `arm_timeout_s = 900` (15 min).