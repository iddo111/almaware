#!/usr/bin/env bash
# Pull every finished LTX clip off the fleet into clips/perceptron/.
# Safe to re-run; scp only what is missing.
set -u
cd "$(dirname "$0")"
mkdir -p clips/perceptron
for h in eran1 eran2 eran4; do
  remote=$(ssh -n "$h" 'ls ~/comfy/output/perceptron/*.mp4 2>/dev/null' || true)
  for r in $remote; do
    b=$(basename "$r")
    if [ ! -s "clips/perceptron/$b" ]; then
      scp -q "$h:$r" "clips/perceptron/$b" && echo "  <- $h $b"
    fi
  done
done
echo "total clips: $(ls clips/perceptron/*.mp4 2>/dev/null | wc -l)"
