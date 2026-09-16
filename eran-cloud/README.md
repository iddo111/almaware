# eran.iddoperez.ai — ERAN Lab

Source for the site served at **eran.iddoperez.ai**.
Cloudflare Pages project: **`eran-swarm`** (see `wrangler.jsonc`).

The site is an open research notebook for ERAN and the surrounding edge-AI work.
Every project on it carries an honest status label, and the labels are the point.

## Structure

| File | What it is |
|---|---|
| `index.html` | The hub — honesty legend, what is actually running, the four tracks, the lab notebook, what we do *not* claim. |
| `eran.html` | Eran: ProtoEran, the vocal cortex, the three named faculties, the HoloBrain north-star, the doctrine. |
| `ants.html` | The Voice Ant Farm: judging protocol, the reigning queen's record, the standing tournament, the autonomy law. |
| `edge.html` | Edge & fleet: the four-node cluster, measured fabric, published failure diagnoses, the federation panel, ALMA-OS, borrowed compute. |
| `lab.html` | Hardware & concept lab: architecture bake-off, connectome models, Shisha Brain (negative result), PROTONEURON, ALMA Language, Yigael. |
| `cloud.html` | The original ERANCLOUD status page (was `index.html` until 2026-08-12). Unchanged content; a back-link was added. |
| `join.html` | ERANCLOUD Windows dry-run instructions. |
| `babble.html` | Honest static WAV player for the saved audio samples. |
| `eran-neuron-lab.html` | Hebrew notes from the physical neuron bench. |
| `alma.css` | The one stylesheet. 100% ours. |
| `join.py` | ERANCLOUD source client; the toy dry-run is the only verified mode. |
| `downloads/` | Source archive, published separately from any installer. |
| `_backups/` | Superseded drafts and pre-truthfix versions. **Excluded from deploys** via `.assetsignore` — kept on disk, never published. |

Zero JavaScript, no framework, no CDN, no external font, no analytics, no third-party
request of any kind. Everything a visitor loads is served from this domain.

## Verified state of the ERANCLOUD client

- `join.py` completes a local toy Local-SGD loop with `--dry-run`.
- No public coordinator, volunteer grid, real Eran replica, or live audio stream is verified.
- Live mode fails closed: it requires an HTTPS coordinator and `--consent yes`; connection
  failure never becomes a silent dry-run.
- The Windows installer remains unreleased until Windows Application Control, install,
  launch, uninstall, and checksum checks pass.

### Verified Windows command

```powershell
Set-Location D:\CLAUDE\eran-cloud
py -3.13 .\join.py --dry-run --provider gcloud --inner-steps 2 --rounds 1
```

This command runs a toy model locally. It does not contribute compute to a live grid.

## Deploying

Deploys are gated: this repository is built and reviewed locally, and published only on
the owner's explicit approval.

```powershell
npx --yes wrangler@latest pages deploy . --project-name eran-swarm --branch main --commit-dirty=true
```

`--project-name` must be given explicitly: `wrangler.jsonc` still carries an older
project name, and the custom domain belongs to `eran-swarm`.

After deploying, confirm that the superseded drafts are **not** reachable — for example
`/index.html.before-truthfix-20260720` should fall through to the hub rather than serve
the old page.
