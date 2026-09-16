# 🎬 CLIPS INSTRUCTIONS — how to generate the 25 Grok Imagine clips

> 🪟 Broken-windows: if a clip does not download, DO NOT ship a broken movie. Fix the clip first (regenerate or fall back to manual paste). No placeholders in the final render.

The 10-minute movie needs **25 Grok Imagine clips** (numbered `01_*.mp4` → `25_*.mp4`, one per Grok row in `shot_list.md`). Two paths — **Path A is preferred** (Claude drives Chrome for you). **Path B is the fallback** (you paste manually). You can also **mix** — start with A, and if any specific clip fails, paste that one manually.

Target folder for every clip: `D:\CLAUDE\perceptron-movie\clips\`
Filenames must be exactly `01_mark_i_lab.mp4`, `02_photocell_grid_reveal.mp4`, … `25_gel_neuron_close_dedication.mp4` (see `shot_list.md` for the full list). Aspect: 16:9. Duration per clip: pick Grok's longest option (typically 6–8s).

---

## 🅐 Path A — Claude drives Grok Imagine via CDP  (PREFERRED)

### Step 1 · Close every Chrome window
Chrome only opens the debug port when it is the **first** Chrome process to start. If a normal Chrome is already running, the debug batch will just attach silently to it and Claude will not be able to see the tabs. So — close them all.

### Step 2 · Double-click `CHROME-DEBUG.bat`
Path (already on your machine):
```
D:\CLAUDE\grok-web-claws\CHROME-DEBUG.bat
```
It launches a fresh Chrome on `localhost:9222` with a dedicated profile stored at `D:\CLAUDE\grok-web-claws\chrome-profile\`. That profile is separate from your regular Chrome, so your normal browsing is not touched.

### Step 3 · Sign in to grok.com in *that* Chrome window
It will open three tabs — `grok.com`, `chatgpt.com`, `gemini.google.com`. Focus the **grok.com** tab and sign in with your usual account (Google or X). This only needs to happen once — the CDP profile remembers you for every future run.

Verify you are signed in: you should see the Grok chat UI, and the top-right avatar should be yours (not a "Sign in" button).

### Step 4 · Tell Claude in chat
Type any of:
> **clips ready**
> or
> **Grok is up, drive it**

Claude will then:
1. Verify CDP is listening on `localhost:9222` (via `alma_webbrain.py tabs` or direct CDP).
2. Find the grok.com tab, navigate to `grok.com/imagine`.
3. Submit prompt 01 from `shot_list.md`, wait for the render (~30–90s).
4. Download the resulting MP4 into `D:\CLAUDE\perceptron-movie\clips\01_mark_i_lab.mp4`.
5. Move on to prompt 02, 03, … 25.
6. Stitch as clips arrive (parallelizes against Grok's queue).

Expected total wall time: **35–55 minutes** for all 25 clips if Grok's SPA behaves and no anti-bot check trips.

### Step 5 · If Claude reports a stuck clip
Grok occasionally queues, throttles, or its SPA re-renders and confuses the automation. Claude will report the specific clip number and prompt. You have two options:
- **Retry**: say "retry clip N" — Claude re-attempts.
- **Manual bailout**: paste that one prompt yourself in the same Chrome (see Path B below for the paste template), download to the right filename, and say "clip N done manually" — Claude continues from N+1.

Do not let a single stuck clip block the whole movie. Bail to manual for that one clip and keep going.

---

## 🅑 Path B — Manual paste  (FALLBACK, always works)

Use this if:
- CHROME-DEBUG.bat won't launch, or
- Signing in to grok.com in the debug profile is a hassle, or
- Grok's anti-bot check is aggressive today, or
- You just prefer to click.

### Step 1 · Open grok.com/imagine in **any** browser you already trust (regular Chrome is fine — no debug port needed for this path).

### Step 2 · Copy prompt 01 from `shot_list.md` (the "Grok Imagine prompt" column of row **01**).

### Step 3 · Paste at grok.com/imagine, hit **Generate**, wait for the video, click **Download**.

### Step 4 · Save the downloaded file to:
```
D:\CLAUDE\perceptron-movie\clips\01_mark_i_lab.mp4
```
Rename if the download name is different. **The filename must match** — the stitch step keys on filename.

### Step 5 · Repeat for prompts 02 → 25. Filenames are in the `shot_list.md` table header of each row (they follow the pattern `NN_slug.mp4`).

### Step 6 · Every 5 clips, ping Claude:
> **clips 01–05 done**
Claude will start stitching the completed batch in parallel while you keep pasting. This turns 45 min of pasting into ~30 min of pasting + rendering-while-you-work.

Expected total wall time: **40–60 minutes** of active clicking. Reliable — no anti-bot risk.

---

## 🅒 Path C — Cannot / do not want to generate Grok clips at all

If for any reason you don't want to touch grok.com right now, the movie still needs 25 video sources. Tell Claude:
> **skip Grok, use the fallback plan**

Claude will regenerate `shot_list.md` swapping every `GROK` row for either:
- an ffmpeg-generated Ken Burns pan on a still image (real historical photo where available, or a scientifically-honest ALMA-rendered SVG frame elsewhere), or
- a text overlay card in the Grok slot,
- so the movie still cuts together end-to-end at 10:00.

Quality is lower without the Grok footage, but the movie will exist. Not the preferred path.

---

## Sanity checklist before starting either path

- [ ] `D:\CLAUDE\perceptron-movie\clips\` exists (empty is fine).
- [ ] `D:\CLAUDE\perceptron-movie\photos\` has the 4 historical stills listed at the bottom of `shot_list.md` (rows 02, 07, 14, 21). Grab those in parallel while clips render — they don't depend on Grok.
- [ ] `D:\CLAUDE\perceptron-movie\music\alma_freygish_psytrance.wav` exists (or a Darwish-style psytrance placeholder for now — replace later).
- [ ] `shot_list.md` is the authoritative source of shot order, prompt text, and filenames. If it disagrees with `GROK_IMAGINE_PROMPTS.md`, `shot_list.md` wins.

---

## What Claude does once all 25 clips + 4 photos are in place

1. Renders the 4 text overlay cards (shots 04, 12, 18, 28) via ffmpeg drawtext — no separate downloads needed.
2. Renders Ken Burns pans on the 4 historical stills via ffmpeg zoompan into the correct shot durations.
3. Trims each Grok clip to its shot window (from `shot_list.md`).
4. Slow-motions shots 01, 05, 22, 25, 30 to 0.5–0.7× as marked.
5. Cross-dissolves within a scene, hard-cuts between scenes.
6. Renders the Hebrew VO via edge-tts `he-IL-AvriNeural` from `script_hebrew.md` (or `script.md`'s English) into `audio/vo.wav`.
7. Ducks the psytrance bed −12 dB under the VO.
8. Burns in the English + Hebrew subtitle tracks.
9. Exports `D:\CLAUDE\perceptron-movie\render\perceptron_movie_v1.mp4` (4K H.264, 16:9).
10. Drops a desktop `.lnk` for you to double-click and watch.

Total render time after all inputs are ready: **~10–15 minutes** on your workstation.

---

## Say-When-Beyond-Me

If **anything** is not working — clip download failing, CDP not attaching, filename mismatch — say so plainly and early. Traffic-light: 🟢 all good, 🟡 partial (say which clip stuck), 🔴 stop and fix. Do not let a broken window sit.
