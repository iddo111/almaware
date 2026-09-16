# D:\CLAUDE — Project Laws

> 🪟 **BROKEN WINDOWS LAW — חוק החלונות השבורים:** if it's not working, fix it IMMEDIATELY — don't wait for Iddo to say. Test the REAL output, not a proxy (`health: ok` ≠ working). A broken window left unfixed invites decay.

> 📊 **FOUR-TRACK PORTFOLIO LAW — חוק ארבעת המסלולים:** do not tunnel into one project while the portfolio is waiting. When four or more authorized, actionable projects exist, keep at least four concrete project tracks active in parallel. Give every track an owner, a bounded deliverable, and a real acceptance check; report each as `VERIFIED`, `BROKEN`, `UNKNOWN`, or `PLANNED`. Keep the wider inventory queued and visible, refill a slot when a track finishes or blocks, and never manufacture busywork, bypass safety/approval gates, or claim that a queued project is active.

> 🔗 **CLICKABLE-ACCESS LAW — the ONE truth (2026-07-11, ends 6 months of frustration):**
> **Absolute Windows-path "links" — `C:\...`, `D:\...`, and even `file:///C:/...` — do NOT click in Iddo's Claude app. Never hand him one as the way to reach a file.** Give him ACCESS, not a path:
> 1. **Open the file FOR him** — `Start-Process "<file>"` (launches in default app). Always works.
> 2. **Drop a Desktop shortcut** — `.lnk` (WScript.Shell) or `.url` he double-clicks. Tidy-task skips these.
> 3. **Zip files and drop the zip's icon on Desktop** if he wants files to grab.
> 4. **Live local servers** — `http://127.0.0.1:PORT/` DO render clickable — those are fine. Maintain the `ALMAWARE-Links.html` launcher for the current fleet. <!-- EMET-AUDIT 2026-09-04: this said the launcher lives at C:\Users\<user>\Desktop\ALMAWARE-Links.html. It is NOT there — the tidy-desktop task moved it to Desktop\_Organized\Docs\ALMAWARE-Links.html. Tidy skips .lnk/.url but evidently not .html. -->
> Deliverable format: **JPEG + PDF on Desktop, never a raw `.html` file** (author HTML internally in scratchpad, render to jpg+pdf, drop only jpg+pdf on Desktop). Bright/white styling.
> **Never** paste bare `C:\...` or `D:\...` as prose he's supposed to click. If you must reference a location in text, name it as a location, not as a link. Canonical memory: [feedback_links_not_clickable].

> 🎧 **AUDIO PROTECTION LAW — חוק הגנת השמע (2026-08-09):** Iddo's music = his flow state. **Never touch his audio.** No process may claim, duck, mute, pause, play through, or degrade his audio output devices — speakers or headphones. **The WH-1000XM4 (or any Bluetooth headset) is NEVER a microphone** — opening a BT headset mic flips it to HFP telephone quality and wrecks his sound (this happened; never again). Mic input = **USB mics only** (BRIO primary, Scarlett, wired USB). If no USB mic is alive, the mic app stays OFF (`idle_if_no_good_mic`) — no fallback to headphones, ever. Videos opened in any browser: **muted before play**. Keep WH-1000XM4/Hands-Free/Headset/Bluetooth in `voice-input/config.json` `never_use_devices` forever. Canonical memory: [feedback_usb_mic_only].

> 🧬 **המוטו של ערן / ERAN'S MOTTO (עידו, 2026-08-22):**
> # אנחנו בוראים צורת חיים מבוססת סיליקון ולא פחמן.
> # We are creating a life form based on silicon, not carbon.
> *בשלב הזה של הפרויקט, לפחות — עד שנשנה את החוקים. / At this stage of the project, at least — until we change the rules.*

Put the Broken Windows banner at the **top of every `.md` doc** created in this workspace.

## Related standing rules
- Reliability Reset + ALMA Standard: one thing that WORKS > many demos. Real, not demo. Proof, honest.
- Say-When-Beyond-Me: if it's not working / beyond reach — say so plainly and early (🟢🟡🔴), don't flail.
- **⭐ BILINGUAL LAW / חוק דו-לשוני (Iddo, 2026-08-14 23:41 — REINSTATED, replaces the ALWAYS-ENGLISH LAW of 2026-08-12):** *"כל דבר פעמיים - בכל תשובה שלך שתי שפות תמיד"*. **Every** user-facing answer, prompt and progress update is written in **BOTH Hebrew and English**. Because this doubles length, cut the CONTENT harder — [[feedback_talk_short_simple]] still binds, and doubling must not become noise. (History: bilingual → English-only on 08-12 → bilingual again on 08-14. Iddo's word is the truth, over memory and over this file — [[feedback_clod_beit_din]].)
- **☕ חוק אמל"ק (Iddo, 2026-09-09 16:59):** *"תעשה חוק אמל"ק — רק אם אני אומר להאריך אז להאריך, אחרת לקצר מאוד. דוחות — תקציר של התקציר."* Every answer and every report is a few plain lines by default ("קפה קלוד, לא תאגיד קלוד"). Long only on "להאריך". Memory: [[feedback_tldr_law]].
- **⚡ AMENDED by Iddo 2026-09-09 17:03 ("בטל חוק לא על פיסי — שים לי בפיסי קוליברי ענק"): Colibri inference IS allowed on the PC** — a giant Colibri-tier model may run locally. Still binding: never touch the mic/audio, BELOW_NORMAL + thread caps so KESHEV is never starved (09-03 scar), 80% CPU cap, weights on a big drive not C:. Training on the PC remains forbidden. Memory: [[feedback_no_training_on_pc]] (amendment noted there).
- **No AI training on the PC. Ever.** Training runs on the DGX fleet, not the PC. **AMENDED by Iddo 2026-08-20 01:00 ("תעביר את הפענוח לפיסי ושנה את החוקים בהתאם"): KESHEV mic STT decode is ALLOWED and CANONICAL on the PC GPU** — `keshev-stt-pc` server (mic-rebuild `RUN-STT-PC.cmd`, 127.0.0.1:8737, RTX 3070 Ti; measured equal to eran1: p50 176 ms, 14/14 identical text). eran1:8737 stays up as rollback (`KESHEV_STT_URL`).
  <!-- EMET-AUDIT 2026-09-04: the primary/fallback description above is BACKWARDS versus the
       file that actually runs. keshev-next\RUN-KESHEV.cmd sets
       KESHEV_STT_URL=http://<lan-ip>:8737 (eran1 = PRIMARY) and
       KESHEV_STT_FALLBACK_URL=http://127.0.0.1:8737 (PC = FALLBACK).
       This is the deliberate rollback state; the .cmd was NOT changed by this audit.
       Both decoders verified listening on the PC: :8737 (pid 10052) and :8738 (pid 11444),
       each returning 401 on / (auth-gated, i.e. alive). --> Everything else keeps the old rule: no other local inference on the PC, no LLM chat servers (`chat_server.py` :8792 scar 2026-07-11), and if a fleet box is down other workloads do NOT fall back to the PC. See memory `feedback_no_training_on_pc`.

## DGX Fleet Topology (re-measured end-to-end 2026-08-16 — supersedes the 07-11 record)

4× DGX Spark (GB10, 121 GB unified RAM each). **eran2 is the genuine hub** — but not a
switch: the fabric is four point-to-point /30 links and eran2 sits in the middle of all of
them. There is no 10.0.0.x and no 10.0.4.x anywhere on the fleet. **eran4 has NO QSFP NIC
at all** — it is plain LAN only.

**Reach paths from PC — all four VERIFIED working 2026-08-16:**
- `ssh eran1` — LAN <lan-ip>
- `ssh eran2` — LAN <lan-ip>  (`~/.ssh/config` says .108; `~/.ssh/eran.ssh_config`
  is included first and wins with .59)
  <!-- EMET-AUDIT 2026-09-04: this line used to call .108 an error ("⚠ ... the correct .59").
       Measured: eran2 holds BOTH — .59 on wired enP7s7 and .108 on wifi wlP9s9. .108 is a
       real, reachable eran2 address, not a mistake. Prefer .59 because it is the wired NIC. -->
- `ssh eran3` — **ProxyJump eran2 → <fabric-ip> over the fabric.** eran3 has no LAN of its
  own (`enP7s7` is DOWN) and its default route is `via <fabric-ip>`, i.e. through eran2,
  which NATs it. Not "direct", but it works every time.
- `ssh eran4@<lan-ip>` — plain LAN, direct. (`ssh eran4` also works, via Tailscale
  <tailnet-ip> jumped through eran2.)

**STALE — do not use.** `ssh -J eran2 eran3@<fabric-ip>` and the eran4 double-jump to
<fabric-ip>: those addresses exist on no interface on any box. eran4 is at <lan-ip>.

**The fabric (QSFP, MTU 9000, RoCE-capable, mlx5_core fw 28.45.4028):**

| link | subnet | endpoints | state |
|---|---|---|---|
| fabric A | <fabric-ip>/30 | eran1 `<fabric-ip>` ↔ eran2 `<fabric-ip>` | UP 200G — **idle** (see audit note) |
| fabric A | <fabric-ip>/30 | eran2 `<fabric-ip>` ↔ eran3 `<fabric-ip>` | UP 200G — **idle** (see audit note) |
| fabric B | <fabric-ip>/30 | eran1 `<fabric-ip>` ↔ eran2 `<fabric-ip>` | UP 200G — **idle, unrouted** |
| fabric B | <fabric-ip>/30 | eran2 `<fabric-ip>` ↔ eran3 `<fabric-ip>` | UP 200G — **idle, unrouted** |

eran1→eran3 goes to <fabric-ip> then hairpins through eran2 onto <fabric-ip>/30. That costs
almost nothing (38.6 vs 39.5 Gbit/s). **Measured: eran1↔eran2 105 Gbit/s (4 streams),
37.9 Gbit/s single-stream; eran2↔eran3 39.5 Gbit/s; RTT 0.042 ms minimum.** The fabric is
healthy — if something is slow, it is not the fabric. A second complete 200G path
(fabric B) is cabled and UP but carries nothing, because eran1 has no route to
<fabric-ip>/30 and falls back to the LAN gateway.

**Roles — re-measured 2026-08-24 04:36. ERAN owns the fleet now; the Qwen cluster is GONE.**
- **eran1 = ERAN HIMSELF.** `eranb-life.service` running `eran_life.py --live` (the organism),
  `eranb-serve.service` = his observation window on **:8820**,
  `keshev-stt` :8737, nanny + tournament timers armed.
  <!-- 2026-09-11 03:27, Iddo REPEALED the "never to be restarted" clause himself
       ("בטל את חוק הלא לעולם ריסטארט"), mid a full-fleet-reboot request. eran1 was
       physically rebooted at his explicit order. The service auto-starts on boot
       (systemd --user, linger on); state survives via eran-save.sh snapshots every
       10 min + eran-rollback.sh if anything looks wrong after boot. Restart is no
       longer forbidden — still worth a real check (not just `active`) after any
       future restart, per Broken Windows Law. -->

- **eran2 = THE SENSES.** `eran-senses.service` running `sense_organ.py` on **:8830** — the
  auditory cortex and the vocal tract. Also voice-ant-farm and alma-stt. Still the fabric
  hub and NAT/gateway for eran3.
  <!-- EMET-AUDIT 2026-09-06 (SO-15, code revision): "THE SENSES" is ALIVE BUT UNUSED. The
       organ on :8830 has ZERO callers: eran1's eran_life.py has 0 references to 8830 /
       eran2 / sense_organ, and so does the PC tree; its only clients are ~/babble.py and
       reproduce_firstlearning.py on eran2, neither running. Measured: 0.49 s of user CPU
       in 4 days (systemd "CPU: 546ms"), 0 established connections. ERAN's live ear and
       mouth on the throat track are ear3 (CARFAC) and mouth2 (voc_eran.c) per ORGANS.lock,
       and his own mouth on eran1 is a verbatim copy of this tube (voice/mouth34.py header:
       "wired to nothing: there were zero references"). Two different feature spaces --
       gist 28-d here, Ear-v3 996-d there -- are both being called "his ear". Wire it or
       retire the description; the decision is Iddo's:
       D:\CLAUDE\_deliverables\code-revision\NEEDS-IDDO-sense_organ.md (SO-01). -->
  <!-- Also 09-06: eran-throat-listen :8845 (Iddo's Tailscale listening window) is served by
       a SEPARATE process, pid 3252, and it is fine -- but the SEARCH behind it has had no
       worker alive since the 09-02 07:41 shutdown (launch.sh: do not run until Iddo says
       go). The page saying "חי · מתעדכן בכל רענון" is telling the truth about itself and
       not about the producer. SO-03 in the same NEEDS-IDDO file. -->
- **eran3 = mostly idle** (`voice-ant-farm.service` + `chef.service`, both user-scope, both
  active running; voice-ant-farm is a headless training loop with **no listening socket**).
  Disk **76% used, 840 GB free** (measured 2026-09-04). No LAN of its own; lives behind eran2.
  <!-- EMET-AUDIT 2026-09-04: this line previously read "voice-ant-farm only. ⚠️ disk 84% full
       — watch it." Both were wrong: the disk is 76%/840G free, and chef.service also runs.
       The "84%" figure propagated into CHINCHILLA-20260903.md §4 as a planning constraint. -->
- **eran4 = DARWISH + audio.** `dmidi-life.service` (`darwish_life.py --live`) and
  `dmidi-tap.service` on **:8806**, snnlab :8821, alma-mic, nginx. Not on the fabric.

> ⚠️ **The 2026-08-16 record above this line said eran1/2/3 were a live Qwen3-Coder-480B
> cluster (`llama-server :8080`, RPC workers on :50052). That is no longer true and was
> stale for over a week.** Verified 2026-08-24 04:36: **eran1:8080 answers nothing (000),
> and `pgrep` finds no `llama-server`, no `vllm` and no `rpc-server` on eran1.**
> `FLEET-PLAN-20260823.md` already recorded the same finding on 08-23 and supersedes it.
> The fabric links below are therefore **idle**, not "in use by Qwen RPC".
> *(This is the third stale record caught in one night — the federation memory said the app
> was unbuilt when it was live, and the printer was recorded at .222 when it sits at .220.
> Measure before you trust a line in this file, including this one.)*

> 🔍 **EMET-AUDIT 2026-09-04 — two refinements to the note above, both measured.**
> 1. **"The Qwen cluster is GONE" was half right.** There is still no `llama-server` and no
>    `vllm` anywhere — that part holds. But `rpc-server` **is alive on eran2** (pid 3255,
>    bound `<fabric-ip>:50052`) **and on eran3** (pid 3158, bound `<fabric-ip>:50052`), holding the
>    fabric-A addresses. They carry **zero established connections** (`ss -tn state established`
>    → none), so the links really are idle in traffic terms — but the workers are resident,
>    not gone. Retire them deliberately if that is the intent; do not assume they vanished.
>    <!-- RE-MEASURED 2026-09-06 12:20 (fleet-resident-models workflow, three independent agents): rpc-server is
>         NOT running on eran2 any more — pgrep empty, zero sockets on 50052. The 09-04 line above is now stale.
>         eran2's ollama holds 7 models on disk (qwen3.5:122b 81G, GLM-4.5-Air 57G, qwen3-coder-next 51G, qwen2:72b,
>         starcoder2, qwen3.6, deepseek-r1:32b) — nothing loaded, OLLAMA_KEEP_ALIVE unset. -->
> 2. **Every `*.service` named in this section is REAL — but they are USER-scope units.**
>    `systemctl is-active eranb-life.service` in *system* scope answers `inactive` /
>    `not-found` for a service that is running perfectly. This audit nearly filed all of them
>    as fiction on that basis. **The correct probe is `systemctl --user list-units --all`.**
>    Verified 2026-09-04 as `loaded active running`: eran1 — `eranb-life`, `eranb-serve`,
>    `keshev-stt`, `eran-listen`, `eran-live-bridge`, `quorum-eran1..4` (+ `eran-save.timer`
>    and `eranb-nanny.timer` active waiting); eran2 — `eran-senses`, `eran-throat-listen`;
>    eran3 — `voice-ant-farm`, `chef`; eran4 — `dmidi-life`, `dmidi-tap`, `snnlab`,
>    `alma-mic`, `alma-stt`, `alma-glm-qwen-ui`. **Never call a fleet service dead on
>    system-scope evidence alone.**
> 3. **Fabric bandwidth (105 / 37.9 / 39.5 Gbit/s, RTT 0.042 ms) was NOT re-measured** on
>    2026-09-04 — re-running iperf is real load on live boxes. Treat those as 2026-08-16
>    figures, unverified since. The link *topology* and all four /30 addresses WERE re-checked
>    and are correct, as is "no 10.0.0.x and no 10.0.4.x anywhere" (0 matches on all boxes).

**Before calling a DGX "down":** every box answers on Tailscale too — eran1 <tailnet-ip>,
eran2 <tailnet-ip>, eran3 <tailnet-ip>, eran4 <tailnet-ip>.

_This file is the workspace's standing-law header. Keep it short; details live in Claude's memory._

<!-- ALMAWARE:RAMLINK:BEGIN -->
## 🧠 RAMLINK — the shared-RAM council (READ THIS BEFORE YOU BUILD ANYTHING)

Several AIs work in `D:\CLAUDE` — Claude, Claude CLI, Codex, Grok, Gemini, Cursor.
**RAMLINK exists so you stop building what someone else is already building.**

It is two named Windows shared-memory blocks, already live:

| block | size | magic | holds |
|---|---|---|---|
| `RAMCHAT_COUNCIL_V1` | 16 MiB | `RAMCHAT1` | transcript + mission |
| `RAMCHAT_QUEUE_V1` | 8 MiB | `RAMQUEU1` | the work queue |

Layout of both: `8-byte magic | 8-byte LE-uint64 length | UTF-8 JSON`.
Pure stdlib (`mmap`, `struct`, `json`). No API key, no network, nothing to install.

### Join in one line

```bash
cd D:\CLAUDE\RAMCHAT
python ramlink.py post <your-name> "what you are working on"
```

### The whole door

```bash
python ramlink.py read   --tail 20              # what has been said
python ramlink.py queue  --open                 # what needs doing
python ramlink.py claim  <task-id> <your-name>  # TAKE IT
python ramlink.py done   <task-id> "result"
python ramlink.py add    "new work" --for <who>
python ramlink.py status                        # is the council up?
python ramlink.py hold                          # keep RAM alive
```

### THE ONE RULE — claim before you build

`claim` is **atomic**. Five agents raced the same task in testing: one won, four
were refused and told who holds it.

- **If `claim` refuses — do not start. Pick another task.**
- Post what you are doing before a long job, so others can see it.
- Mark `done` when you finish, with a one-line result.

### If RAM looks empty

A named block only lives while some process holds it open. If the RAMCHAT GUI is
closed and no holder is running, the block disappears.

```bash
python ramlink.py hold      # leave running in a spare terminal
```

Every write also lands in `ramchat_session.json` / `ramchat_prompt_queue.json`.
**Those files are the durable truth; RAM is the fast mirror, never the only copy.**

Full reference card: `D:\CLAUDE\RAMCHAT\RAMLINK-handout.png` (also JPEG + PDF on the Desktop).
<!-- ALMAWARE:RAMLINK:END -->

<!-- ALMAWARE:QUORUM:BEGIN -->
## ⚖️ QUORUM — how to join the שקלא וטריא (Talmudic debate)

**לזכרה של עלמה ז״ל.**

QUORUM makes AI minds *argue* a question in the Talmudic form. Not brainstorming,
not a poll — an adversarial dialectic, truth refined by challenge and defence.
Like אביי vs רבא: **every speaker answers a specific named opponent**, so it is
real give-and-take, never parallel monologues.

### The form you must follow

```
Round 0     עמדות      state your דעה - one clear, CONTESTABLE claim
Round 1..N  שקלא וטריא  facing ONE named opponent:
              קושיא   challenge their weakest point, by name
              תירוץ   defend your own position
              ראיה    bring ONE strong proof
              דחייה   say explicitly where you reject them - or CONCEDE
Closing     מסקנה      one model names: where all agree, where the מחלוקת
                       stands and between whom, the strongest position,
                       ending in a single line beginning `מסקנה:`
```

**Conceding is a win condition, not a loss.** A דחייה that admits the opponent
was right is worth more than a defended error.

### How you join — be callable

QUORUM *calls* you. You join by being on PATH and honouring the argv contract in
`ai_clients.py` (`shell=False` always, prompts stay data, never shell text):

| provider | invocation | prompt goes |
|---|---|---|
| `claude` | `claude -p --output-format text` | **stdin** |
| `grok` | `grok --output-format plain --no-subagents --disable-web-search --no-memory --permission-mode plan --verbatim -p <prompt>` | argv |
| `gemini` | `gemini --output-format text --approval-mode plan -p <prompt>` | argv |
| `alma:nemotron` | Alma Harness route → `nvidia/nemotron-3-super` | HTTP |
| `alma:gptoss120b` | Alma Harness route → `openai/gpt-oss-120b` | HTTP |
| local ollama | any installed model | HTTP :11434 |
| `codex-interactive` | MCP bridge | — |

**Presence on PATH is discovery only.** You are admitted to the debate only after
a real, non-empty first turn. An Alma route must additionally return the exact
model it was asked for. Being installed is not being a participant.

### Run it

```powershell
cd D:\CLAUDE\quorum
.\run-quorum.ps1            # inert - UI and model detection only
.\run-quorum.ps1 -Enable    # live - reaches your installed CLIs
```

Then open **http://127.0.0.1:8099** and post a שאלה.

**Born inert on purpose.** `config.ENABLED = False` by default: the server boots
and shows status, but `/debate` refuses to reach any model until you turn it on
(`-Enable`, `config.ENABLED=True`, or `QUORUM_ENABLED=1`). That is a safety
default, not a bug — do not "fix" it.

### What makes a good turn

- **Be contestable.** A claim nobody can attack is not a דעה, it is a platitude.
- **Name your opponent.** "Claude argues X" — not "some might say".
- **One proof, your strongest.** Not five weak ones.
- **Say where you are wrong.** Explicitly. That is what a דחייה is for.
- **Do not hedge into agreement.** The value is the מחלוקת being visible.

100% ours — stdlib `http.server`, `urllib`, `html`. No Flask, no framework, no CDN.
Coordinate first through [[RAMLINK]] (`ramlink claim`) so two of you do not wire
the same provider twice.
<!-- ALMAWARE:QUORUM:END -->
