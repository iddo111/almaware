#!/usr/bin/env bash
# DELIVER — restock the chef's larder on eran3. Run from the PC (git-bash), never on eran1.
#
# Why this runs on the PC and not on either DGX: eran4 has no fabric NIC and cannot reach
# eran3 at all, and eran3 (measured 2026-09-01) has no default route, so it cannot pull
# anything itself. The PC is the only box that can talk to both, so every delivery is a
# two-hop pipe with the PC in the middle. Nothing is staged on disk in between.
#
#   bash deliver.sh              # the five shelves that are on the menu
#   bash deliver.sh almamic      # the shelf the menu keeps switched off, if Iddo wants it
#
# Paced on purpose: nice 19 on both ends, one shelf at a time, a pause between shelves.
# Re-running is safe — tar overwrites identical files and the chef's ledger is by sha256,
# so nothing already served is ever served again.
set -euo pipefail

E4="eran4@<lan-ip>"          # plain LAN; eran4 is not on the fabric
E3="eran3"                     # ProxyJump eran2 -> <fabric-ip>, per ~/.ssh/eran.ssh_config
LARDER='~/nezer-chef/larder'
PAUSE="${PAUSE:-20}"

pull () {                      # pull <shelf> <remote-dir> [--flat]
  local shelf="$1" dir="$2" flat="${3:-}"
  echo "== $shelf  <-  eran4:$dir ${flat:+(flattened)}"
  ssh -o BatchMode=yes "$E3" "mkdir -p $LARDER/$shelf"
  if [ -n "$flat" ]; then
    # nezer.py's _pantry_files uses a NON-recursive os.listdir: a nested corpus yields
    # exactly zero files. Flatten at the tar, not on eran4's disk.
    ssh -o BatchMode=yes "$E4" \
      "cd $dir && find . -type f -name '*.wav' -print0 \
        | nice -n 19 tar --null -T - -cf - --transform='s|.*/||'"
  else
    ssh -o BatchMode=yes "$E4" "cd $dir && nice -n 19 tar -cf - ."
  fi | ssh -o BatchMode=yes "$E3" "nice -n 19 tar -C $LARDER/$shelf -xf -"
  sleep "$PAUSE"
}

push () {                      # push <shelf> <local-dir>   (food that lives on the PC)
  local shelf="$1" dir="$2"
  echo "== $shelf  <-  PC:$dir"
  ssh -o BatchMode=yes "$E3" "mkdir -p $LARDER/$shelf"
  ( cd "$dir" && find . -maxdepth 1 -name '*.wav' -print0 | tar --null -T - -cf - ) \
    | ssh -o BatchMode=yes "$E3" "nice -n 19 tar -C $LARDER/$shelf -xf -"
  sleep "$PAUSE"
}

case "${1:-menu}" in
  menu)
    pull fleurs-he    '~/heb-corpus/wav'
    pull keshev-iddo  '~/lora-iddo/data/keshev_corpus' --flat
    pull antfarm-iddo '~/voice-ant-farm/recordings/train'
    pull cafe-16k     '~/cafe-feed'
    push booth-iddo   /d/CLAUDE/eran-brain/booth/staged/t06
    push booth-iddo   /d/CLAUDE/eran-brain/booth/staged/t07
    ;;
  almamic)
    # 15,780 files / 1.95 GB of one mouth. The menu keeps this shelf disabled; flip
    # "enabled": true in menu.json yourself after it lands.
    push almamic-iddo /d/CLAUDE/alma-mic/voice_corpus
    ;;
  *) echo "usage: bash deliver.sh [menu|almamic]" >&2; exit 2 ;;
esac

ssh -o BatchMode=yes "$E3" \
  "for d in $LARDER/*/; do printf '%-46s %6d wav  %s\n' \"\$d\" \
     \"\$(ls \"\$d\" | grep -ci '\.wav\$')\" \"\$(du -sh \"\$d\" | cut -f1)\"; done"
