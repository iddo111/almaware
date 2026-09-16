# Nemotron rank-fix cutover and rollback

The cutover keeps every pre-fix container. Nothing is removed.

- DGX1 live API becomes `nemotron-cluster-triton-pre-rankfix`.
- DGX1 old trial `nemotron-cluster` becomes `nemotron-cluster-trial-pre-rankfix`.
- DGX1 old Ray head becomes `nemotron-ray-head-unpatched`.
- DGX2 and DGX3 old Ray workers each become `nemotron-ray-worker-unpatched`.
- New canonical containers use `nemotron-ray-head`, `nemotron-ray-worker`, and
  `nemotron-cluster`, all from `vllm-ray-nemotron-pp:v0.20.0-rankfix`.

Rollback is: stop the new API and Ray containers; rename the new canonical
containers with a `-failed-rankfix` suffix; rename the three unpatched Ray
containers back to their canonical names and start them; then start
`nemotron-cluster-triton-pre-rankfix`. The retained API still binds port 8000.
