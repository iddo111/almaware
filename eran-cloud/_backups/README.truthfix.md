# ERANCLOUD · truth-first local demo

Current verified state:

- The static site and both WAV files work.
- `join.py` completes a local toy Local-SGD loop with `--dry-run`.
- No public coordinator, volunteer grid, real Eran replica, or live audio stream is verified.
- Live mode fails closed: it requires an HTTPS coordinator and `--consent yes`; connection failure never becomes a silent dry-run.
- The Windows MSI remains unreleased until Windows Application Control, install, launch, uninstall, and checksum checks pass.

## Verified Windows command

```powershell
Set-Location D:\CLAUDE\eran-cloud
py -3.13 .\join.py --dry-run --provider gcloud --inner-steps 2 --rounds 1
```

This command runs a toy model locally. It does not contribute compute to a live grid.

## Files published by the site

- `index.html` — measured status and downloads.
- `join.html` — Windows dry-run instructions.
- `join.py` — source client; toy dry-run is the only verified mode.
- `babble.html` — honest static WAV player.
- `downloads/eran-cloud-source.zip` — source and documentation, separate from any installer.

The old `git.almaware` and `grid.almaware` examples were placeholders and are no longer presented as runnable commands.
