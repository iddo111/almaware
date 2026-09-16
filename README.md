# ALMAWARE Projects

Copyright Iddo Perez. All rights reserved (no license granted yet).

## English

This repository is a sanitized snapshot of source code and documentation from
Iddo Perez's personal AI/hardware/research workspace (`D:\CLAUDE`), published
2026-09-16.

It was built by an automated script (`publish_projects.py`, included in this
repo's history/tooling notes on request) that:
- copied only plain-text source and docs (code, markdown, config -- no
  binaries, no audio/video, no models, no archives) from an allowlist of file
  extensions, capped at 1 MB per file (200 KB for JSON);
- excluded caches, virtual environments, vendored/third-party SDKs (e.g.
  installed copies of gcloud, Blender, Ghidra, OrcaSlicer), build output,
  logs, recordings, session/auth state, and known personal-data folders;
- scanned every remaining file's content against a deny-list and dropped the
  WHOLE file on any hit -- API keys/tokens, private key blocks, phone
  numbers, and private personal material. PTSD and trauma-care material is
  intentionally included;
- redacted internal network details that survived (tailnet hostnames/IPs,
  LAN IPs, the local Windows username) to placeholders rather than exposing
  home-network topology;
- was independently re-scanned by a second, separately-written script before
  this repository was created.

This repository is currently **PRIVATE**. Whether and when any part of it
becomes public is a separate decision Iddo makes later, by hand, after his
own review -- this publish step does not make that call.

The original workspace's own git history was never touched and is not part
of this repository; this is a fresh copy with no history.

## עברית

המאגר הזה הוא תמונת מצב מסוננת של קוד ותיעוד מסביבת העבודה האישית של עידו
פרץ בתחום AI/חומרה/מחקר (`D:\CLAUDE`), פורסם ב-16.9.2026.

נבנה בסקריפט אוטומטי שהעתיק רק קבצי טקסט (קוד, מסמכים, קונפיגורציה -- לא
תמונות, אודיו, מודלים או ארכיונים), החריג תיקיות מטמון/סביבות וירטואליות/
ספריות צד-שלישי מותקנות, קבצי לוג, הקלטות, מצבי הזדהות, ותיקיות מידע אישי
ידועות, וסרק כל קובץ שנותר מול רשימת נושאים אסורים -- מפתחות/סודות, מספרי
טלפון וחומר אישי פרטי. תוכן על PTSD וטיפול בטראומה נכלל בכוונה.

כתובות רשת פנימיות שנשארו (שמות/כתובות tailnet, כתובות LAN, שם המשתמש
בווינדוס) הוחלפו במציין-מקום גנרי.

המאגר הזה **פרטי** כרגע. אם ומתי חלק ממנו יהפוך לציבורי היא החלטה נפרדת
שעידו יקבל בעצמו, בעתיד, אחרי בדיקה שלו -- שלב הפרסום הזה לא מכריע בכך.

היסטוריית ה-git המקורית של סביבת העבודה לא נגעה בה ואינה חלק ממאגר זה; זהו
עותק חדש ללא היסטוריה.

## Projects included / פרויקטים כלולים

- ALMAWARE-LAMP-LAB
- ALMAWARE-POSTERS
- RAMCHAT
- alma-beat
- alma-brain
- alma-brain2
- alma-comfy
- alma-consolidation
- alma-core
- alma-draughtsman
- alma-edu
- alma-enhancer
- alma-federation
- alma-figure
- alma-fs-mcp
- alma-govern
- alma-gptoss120b-cloud-worker-20260721
- alma-headscan
- alma-language
- alma-larynx
- alma-mail-mcp
- alma-master
- alma-memorial-figurine
- alma-mic
- alma-mic-android
- alma-mic-android-v2
- alma-mic-linux
- alma-mic-release
- alma-optical-perceptron
- alma-os-tdeck
- alma-pi
- alma-picks
- alma-quest
- alma-realworld-safety
- alma-recall
- alma-second-brain
- alma-second-brain-system
- alma-tablet
- alma-thermos
- alma-vr
- alma-web-lab
- almaware-cockpit
- almaware-downloads-truthfix
- almaware-hub
- almaware-hud
- almaware-standard-site
- almaware-watchdog
- almido
- ant-farm
- ant-wall
- antvoice-190m
- book-scanner
- cafe-claude
- cardputer-adv-tadiran-ir
- cave-wall-brain-sim
- cnc
- cnc-parts
- coder-base
- codex-fabric-watchdog
- colibri-pc
- command-center
- computer-use
- darwish-ai
- darwish-midi
- dgx-qwen3-coder
- digibrain
- dispatch-fix
- dj-alma
- docs
- doron
- ear-ruling
- emdr
- eran-audio
- eran-avatar
- eran-brain
- eran-cloud
- eran-coder-pack
- eran-dashboard
- eran-encyclopedia
- eran-federation-app
- eran-grid
- eran-live
- eran-movie
- eran-recroom
- eran-token-220
- eran0
- eran2
- ezra-hasofer
- fleet
- fleet-chat
- fleet-mode
- football
- foreman
- foxalien-foodhead
- foxalien-xe-pro-jetson-control
- fun-neuromorphic-lab
- galaxy-a70-bridge-pwa
- game-baal-tefillah
- game-munich
- gpt-oss-120b-training-gui
- gptoss-training
- guitar-picks-iddo
- hebrew-ant-holobrain
- hebrew-corpus
- helios
- hub-mirror
- iddo-harness
- infra-rebuild
- joint-holder
- keshev-2
- keshev-4d
- keshev-6
- keshev-autotrain
- keshev-b
- keshev-fable
- keshev-lora
- keshev-next
- keshev-qwen
- keshev-voicefull
- kof
- limud-keshev
- listen
- listen-ba
- maintenance
- maker-project-portfolio
- master-modeler
- matzav
- melumad
- merch
- mic-rebuild
- mikdash
- miko
- model-forensics
- murphy
- nachman
- nemotron-runtime
- oneroom
- optic-loop
- otiyot-ratsot
- ozen
- patches
- pc-thermal
- perceptron-movie
- pico-lafvin-display
- picobricks-neuron
- pong-alma
- pongo-dave
- quorum
- quorum-site
- qwen-fleet-train
- qwen-fullweight-dual-spark
- qwen-fullweight-train-parked
- qwen480-taste
- research
- robbie
- safa-achat
- sdr-lab
- second-brain
- security-audit-swarm
- sharpen
- shlomo
- site-art
- site-keepalive
- snn-lab
- story
- submarine-internal-spiral-propulsor
- tab-a7-linux
- talking-heads-vocal-loop
- termux-claude-setup
- tokensave
- tools
- trance-music-ai
- unihiker-k10-hebrew-lab
- vipassana
- voice-ant-farm
- voice-input
- water-computer
- web-ai-harness
- whisper-iddo
- workshop-builds
- xiao-rp2350-bringup
- yigal
- zener-neuron
