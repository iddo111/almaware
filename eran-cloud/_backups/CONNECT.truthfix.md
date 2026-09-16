# ERANCLOUD tester connection contract

## Verified today

Only the local toy dry-run is available:

```powershell
Set-Location D:\CLAUDE\eran-cloud
py -3.13 .\join.py --dry-run --provider gcloud --inner-steps 2 --rounds 1
```

Expected sequence: register (dry-run), pull (dry-run), two local AdamW steps, delta metadata, push (dry-run), done.

## Not available today

- no public coordinator URL;
- no public Git host at `git.almaware`;
- no verified three-volunteer-node round trip;
- no real Eran weights or public training shard;
- no live audio stream;
- no released Windows MSI.

## Windows prerequisites

```powershell
py -3.13 --version
py -3.13 -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

Python is invoked as `py -3.13` on Windows. PowerShell does not use `\` as a line continuation; keep the verified demo on one line.

## Live-mode safety contract

Future live mode must use a real HTTPS coordinator, explicit `--consent yes`, authenticated enrollment, public-only data, and a published checksum. If the coordinator fails, the client exits non-zero and does not switch to simulation.

Until those requirements are met, testers should run only `--dry-run` and treat all output as a local simulation.
