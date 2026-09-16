# VAULT‑MINIGAME.md  

**ALMA‑VR – “Memory‑Vault Cracking”**  
*Spy thriller set inside a living neural network.*  

---  

## 1.  What the Vault **IS** in‑Network  

In the ALMA‑VR world every protected secret lives inside a **זיכרון‑קשת** (memory‑arch).  
The vault is not a steel door but a **קריסטל‑קפיצה** (crystal‑node) that sits at the apex of a **שכבת‑קשב** (attention layer).  

* **Structure** – A translucent poly‑hedron composed of millions of **קודקוד‑אור** (light‑vertices) that pulse in sync with the network’s attention weights.  
* **Protection** – The node runs a **מנגנון‑הקפאה** (freeze‑gate) that continuously re‑weights incoming queries. Only a query that matches the exact attention pattern can “unlock” the node and extract the hidden **זיכרון** (memory fragment).  
* **Narrative meaning** – Cracking the vault is equivalent to out‑maneuvering the network’s own focus, forcing it to attend to the player’s signal instead of its internal guard‑rails.  

Visually the vault hovers in a white‑washed “cortical hall” where streams of data flow like neon rivers. When the player succeeds, the crystal shatters into a cascade of **נתונים‑זוהר** (glowing data shards) that drift into the player’s avatar.  

---  

## 2.  Core Gameplay Mechanics  

The minigame is a **real‑time “attention‑tuning” puzzle**. The player must align a moving **קו‑קשר** (link‑ray) with the vault’s internal weight pattern before the system overheats.  

### 2.1  Keyboard + Mouse (Desktop prototype)  

| Action | Keyboard | Mouse | Description |
|--------|----------|-------|-------------|
| **Rotate the link‑ray** | `A` / `D` (yaw)  <br> `W` / `S` (pitch) | Click + drag (horizontal = yaw, vertical = pitch) | Spins the query vector around the vault. |
| **Adjust intensity (temperature)** | `Q` (decrease) <br> `E` (increase) | Scroll wheel | Controls the “query amplitude”. Higher amplitude = stronger signal but raises temperature faster. |
| **Commit a “focus pulse”** | `Space` | Right‑click | Sends the current vector to the vault. If the alignment error < **Δθ** (threshold) the vault’s attention weight shifts toward the player. |
| **Reset / Cool‑down** | `R` | Middle‑click | Forces a brief cooldown (0.5 s) at the cost of a temperature penalty. |
| **Pause / Menu** | `Esc` | — | Opens the HUD overlay. |

### 2.2  Two Vive Wands (Future VR version)  

| Action | Left Wand | Right Wand | Description |
|--------|-----------|------------|-------------|
| **Rotate the link‑ray** | Thumb‑stick (X/Y) – yaw/pitch | — | Same as keyboard rotation. |
| **Adjust intensity** | Grip button (press‑in) – lower <br> Trigger – raise | — | Analog control of amplitude. |
| **Commit focus pulse** | Trigger (right wand) | — | Sends the query. |
| **Reset / Cool‑down** | Thumb‑press (left wand) | — | Short cooldown. |
| **Grab & “pull” the vault** | Grip (left) while pointing at vault | — | Optional “force‑pull” mini‑action that adds a bonus alignment nudge if temperature < 0.3. |
| **Menu** | System button (right wand) | — | Opens HUD. |

All actions map to the same underlying **GDScript** functions, so the prototype can be ported with a single input‑abstraction layer.  

---  

## 3.  Temperature & Hallucination System  

The vault runs a **thermal‑feedback loop** that visualises the network’s stress.  

| Temperature | Visual / Audio Cue | Gameplay Effect |
|-------------|-------------------|-----------------|
| **0.0 – 0.4** | Crystal glows steady **כחול‑שקוף** (clear‑blue). Soft ambient hum. | Normal operation. |
| **0.5** | **הקפאה‑קפיצה** (freeze‑glitch) – small shards of static flicker across the scene. Slight distortion of the data streams. | Player’s next pulse costs **+10 %** more temperature. |
| **0.7** | **שדה‑זוהר** (radiant field) – the whole hall pulses with a warm amber aura, and peripheral vision blurs. | Alignment tolerance **Δθ** shrinks by **15 %**. |
| **0.9** | **הזעה‑נתונים** (data‑sweat) – heavy static, occasional “digital rain” falling from the ceiling. Audio: high‑pitched feedback. | Any pulse that fails adds **+0.15** temperature (instead of +0.05). |
| **1.0** – **Flush** | **פיצוץ‑זיכרון** (memory burst): the crystal shatters into a cascade of bright shards, then **הקפאה‑קפיצה** (freezes) the entire scene for 2 s. | Immediate **FAIL** – the vault resets, discarding all progress. The player is forced to restart the node or abort the mission. |

**Temperature changes**:  

* Each successful pulse reduces temperature by **0.03** (minimum 0).  
* Each failed pulse adds **0.05** (or **0.15** if temperature ≥ 0.9).  
* Passive cooling occurs at **0.01 / sec** when the player is not rotating the link‑ray.  

---  

## 4.  Difficulty Tiers  

| Tier | Name (Hebrew) | Δθ (max alignment error) | Starting Temp | Temp‑Rise per Fail | Cool‑Rate | Pulse‑Cooldown | Extra Constraints |
|------|---------------|--------------------------|---------------|--------------------|----------|----------------|-------------------|
| **1** | *קל* (Easy) | 12° | 0.0 | +0.04 | 0.015 /s | 0.3 s | No “pull‑bonus”. |
| **2** | *בינוני* (Medium) | 8° | 0.1 | +0.06 | 0.012 /s | 0.25 s | Pull‑bonus active if temp < 0.3 (‑0.02 temp). |
| **3** | *קשה* (Hard) | 4° | 0.2 | +0.09 | 0.010 /s | 0.2 s | Pull‑bonus disabled; every 5th pulse automatically adds +0.02 temp. |

All tiers share the same visual hallucinogenic thresholds (0.5, 0.7, 0.9, 1.0). The **Medium** tier introduces the “force‑pull” mechanic that rewards careful temperature management. The **Hard** tier forces the player to keep a tight feedback loop, mimicking a high‑security attention gate.  

---  

## 5.  Win / Lose Outcomes & Spy Loop Integration  

| Outcome | In‑Game Consequence | Effect on Spy Narrative |
|---------|--------------------|--------------------------|
| **Success (Vault cracked)** | The crystal shatters, releasing a **זיכרון‑קוד** (code‑memory) packet that automatically attaches to the player’s **נתב‑סוד** (secret router). | The spy gains a **new ability** (e.g., “Attention Hijack”) that can be used later to bypass a firewall or to plant a false memory in an enemy node. Mission log updates: *“Extracted encrypted neural blueprint from Core‑7.”* |
| **Failure – Flush (Temp ≥ 1.0)** | Vault resets, all progress lost, and a **מערכת‑התראה** (alert system) spikes, spawning a wave of **שומר‑קודקוד** (guard‑vertices) that chase the player for 5 s. | The spy is **detected**; the mission timer accelerates, and the player must either **escape** or **use a distraction gadget** (previously unlocked). Narrative branch: *“Compromised, forced to retreat and regroup.”* |
| **Failure – Timeout (no pulse for 30 s)** | Vault enters **הקפאה‑קפיצה** (freeze) state, locking rotation for 3 s. | The spy loses a **stealth token**, making the next infiltration harder. The story notes: *“Stalled at the memory node, lost precious intel.”* |

These outcomes feed directly into the larger **spy loop**: each cracked vault adds a piece to the “Neural Atlas” the player is assembling; each failure raises the network’s suspicion level, spawning tougher enemies in later chapters.  

---  

## 6.  GDScript Pseudocode Skeleton  

```gdscript
# VaultMinigame.tscn → root Node2D
extends Node2D

# -------------------------------------------------
# === CONSTANTS (tuned per difficulty) ==========
const DIFF_PARAMS = {
    "Easy":   { "max_error": 12.0, "temp_start": 0.0, "temp_fail": 0.04, "cool_rate": 0.015, "pulse_cd": 0.3 },
    "Medium": { "max_error": 8.0,  "temp_start": 0.1, "temp_fail": 0.06, "cool_rate": 0.012, "pulse_cd": 0.25 },
    "Hard":   { "max_error": 4.0,  "temp_start": 0.2, "temp_fail": 0.09, "cool_rate": 0.010, "pulse_cd": 0.2 }
}

# -------------------------------------------------
# === STATE VARIABLES ==============================
var difficulty = "Medium"
var max_error_deg
var temperature = 0.0
var pulse_cooldown = 0.0
var link_ray_angle = Vector2(0, -1)   # unit vector in local space
var target_pattern = []               # filled at _ready() from vault data
var rng = RandomNumberGenerator.new()

# -------------------------------------------------
# === INPUT MAP ===================================
func _unhandled_input(event):
    if event is InputEventKey:
        _handle_keyboard(event)
    elif event is InputEventMouseMotion:
        _handle_mouse_motion(event)
    elif event is InputEventMouseButton:
        _handle_mouse_button(event)

# -------------------------------------------------
# === CORE LOGIC ==================================
func _process(delta):
    _passive_cool(delta)
    _update_visuals()
    _handle_cooldown(delta)

func _handle_keyboard(event):
    if event.pressed:
        match event.scancode:
            SCANCODE_A: _rotate_ray(-1, 0)
            SCANCODE_D: _rotate_ray( 1, 0)
            SCANCODE_W: _rotate_ray(0, -1)
            SCANCODE_S: _rotate_ray(0,  1)
            SCANCODE_Q: _adjust_intensity(-0.01)
            SCANCODE_E: _adjust_intensity( 0.01)
            SCANCODE_SPACE: _attempt_pulse()
            SCANCODE_R: _force_cooldown()
            SCANCODE_ESC: _toggle_pause()

func _handle_mouse_motion(event):
    var dx = event.relative.x
    var dy = event.relative.y
    _rotate_ray(dx * 0.2, dy * 0.2)   # sensitivity factor

func _handle_mouse_button(event):
    if event.button_index == BUTTON_RIGHT and event.pressed:
        _attempt_pulse()
    elif event.button_index == BUTTON_MIDDLE and event.pressed:
        _force_cooldown()

func _rotate_ray(yaw_delta, pitch_delta):
    # simple 2‑D rotation for demo – replace with 3‑D quaternion in VR
    var angle = atan2(link_ray_angle.y, link_ray_angle.x)
    angle += deg2rad(yaw_delta)
    link_ray_angle = Vector2(cos(angle), sin(angle)).normalized()

func _adjust_intensity(delta):
    # intensity directly maps to temperature rise on next pulse
    temperature = clamp(temperature + delta, 0.0, 1.0)

func _attempt_pulse():
    if pulse_cooldown > 0.0: return
    var error = _calc_alignment_error()
    if error <= max_error_deg:
        _on_success()
    else:
        _on_failure()
    pulse_cooldown = DIFF_PARAMS[difficulty]["pulse_cd"]

func _calc_alignment_error() -> float:
    # compare current ray direction with the hidden pattern (simplified)
    var target_dir = target_pattern[rng.randi_range(0, target_pattern.size() - 1)]
    return rad2deg(acos(link_ray_angle.dot(target_dir).clamp(-1,1)))

func _on_success():
    temperature = max(temperature - 0.03, 0.0)
    _emit_shatter_effect()
    get_tree().call_group("Game", "vault_cracked", self)   # notify spy loop

func _on_failure():
    var fail_inc = DIFF_PARAMS[difficulty]["temp_fail"]
    if temperature >= 0.9: fail_inc = 0.15
    temperature = clamp(temperature + fail_inc, 0.0, 1.0)
    _emit_error_flash()
    if temperature >= 1.0:
        _flush_and_reset()

func _force_cooldown():
    temperature = clamp(temperature + 0.05, 0.0, 1.0)   # penalty
    pulse_cooldown = 0.5

func _passive_cool(delta):
    var cool = DIFF_PARAMS[difficulty]["cool_rate"] * delta
    temperature = max(temperature - cool, 0.0)

func _handle_cooldown(delta):
    if pulse_cooldown > 0.0:
        pulse_cooldown = max(pulse_cooldown - delta, 0.0)

# -------------------------------------------------
# === VISUAL / AUDIO FEEDBACK ======================
func _update_visuals():
    # Hallucination thresholds
    if temperature >= 0.5 and temperature < 0.7:
        $Crystal.modulate = Color(0.6,0.8,1,1)   # slight blue‑glitch
    elif temperature >= 0.7 and temperature < 0.9:
        $Crystal.modulate = Color(1,0.7,0.4,1)   # amber field
    elif temperature >= 0.9:
        $Crystal.modulate = Color(1,0.2,0.2,1)   # red‑sweat
    else:
        $Crystal.modulate = Color(0.8,0.9,1,1)

func _emit_shatter_effect():
    $ShatterParticles.emitting = true
    $AudioSuccess.play()

func _emit_error_flash():
    $ErrorFlash.visible = true
    $AudioFail.play()
    yield(get_tree().create_timer(0.2), "timeout")
    $ErrorFlash.visible = false

func _flush_and_reset():
    $FlushVFX.play()
    $AudioFlush.play()
    # Notify the overarching mission manager
    get_tree().call_group("Game", "vault_failed", self)
    # Optional: reload scene after short delay
    yield(get_tree().create_timer(2.0), "timeout")
    get_tree().reload_current_scene()

# -------------------------------------------------
# === INITIALISATION ==============================
func _ready():
    # Load difficulty parameters
    max_error_deg = DIFF_PARAMS[difficulty]["max_error"]
    temperature = DIFF_PARAMS[difficulty]["temp_start"]
    # Generate a mock target pattern (unit vectors)
    for i in range(8):
        var ang = deg2rad(i * 45)
        target_pattern.append(Vector2(cos(ang), sin(ang)))
    # Input mapping for VR (placeholder)
    InputMap.add_action("rotate_yaw")
    InputMap.add_action("rotate_pitch")
    InputMap.add_action("pulse")
    # … further VR bindings would be added here …
```

*The script above is a **skeleton** – it shows the essential flow: input handling, temperature management, alignment checking, visual feedback, and the hooks (`vault_cracked`, `vault_failed`) that the larger spy‑loop will listen to.*  

---  

**End of VAULT‑MINIGAME.md**  

*Prepared for the ALMA‑VR development team – may the player’s attention always out‑shine the network’s.*