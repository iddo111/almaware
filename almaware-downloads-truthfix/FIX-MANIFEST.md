# Almaware download-link staging fix

Deploy nothing from this folder until all links are GET-verified again.

Targets:

- `iddoperez-almaware/index.html` -> Cloudflare Pages project `iddoperez-almaware` (custom domain `almaware.iddoperez.ai`).
- `almaware-iddoperez/index.html` -> duplicate Pages project `almaware-iddoperez`.

Exact change: eleven public GitHub repositories use default branch `master`, but
the deployed pages request `main.zip`. The staging script changes only those
eleven allowlisted archive URLs. `messenger-hub` correctly remains on `main`.
