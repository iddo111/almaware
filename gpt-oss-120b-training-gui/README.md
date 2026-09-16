# GPT-OSS 120B Training Console

Local, fail-closed control surface for the Eran1 + Eran2 GPT-OSS 120B lane.

Current verified route:

- Windows GUI: `http://127.0.0.1:8766/`
- SSH tunnel: `127.0.0.1:11435` to Eran1 `127.0.0.1:11434`
- Exact inference model: `gpt-oss:120b`
- Training weights: `/home/eran{1,2}/models/gpt-oss-120b`
- Native original-tensor project: `/home/eran1/eran/gptoss-native-attention-sft`
- Literal all-parameter engineering project: `/home/eran1/eran/gptoss-fullweights-distributed`

Run `launch.ps1`. The console rejects LoRA, QLoRA, PEFT, adapters, and adapter
merges as substitutes for native-weight training. Training remains locked even
if the legacy `GPTOSS_ENABLE_TRAINING=1` environment variable is present.

The required acceptance chain is: changed original GPT-OSS tensor hash,
complete derived checkpoint, fresh-process reload, nonempty exact-model
generation, and held-out evaluation. The current native attention runner is
still blocked on its MXFP4 backward qualification and has no verified launcher,
so this GUI must display `Locked`. Inference and read-only inspection remain
separate and available only when their own live checks pass.

An Ollama model tag is route evidence only. The GUI shows `Route listed` until
that same visible GUI submits a fresh `GPTOSS-GUI-*` nonce and receives
one completed, nonempty response from the exact `gpt-oss:120b` identity
containing that nonce. Verification is bound to the current model digest and a
five-minute GUI-session TTL. Per-node available memory, GPU compute processes,
and containers are reported under the lane they actually gate; `Copies
present` means checkpoint copies only and is never a training-readiness claim.

The implemented native project is explicitly the Eran1 attention-only
engineering lane (144 BF16 q/k/v/o tensors). It is not the separate two-node,
all-parameter request; that remains an unimplemented engineering lane under
`gptoss-fullweights-distributed`. Eran2 resource/workload blockers therefore
gate only the two-node all-parameter lane, not the Eran1-only experiment.

The **Test tool use** control runs three live, deterministic checks against the
exact model: exact argument emission, least-privilege tool selection, and
approval routing. The tools are mocks; the test validates calls but executes no
filesystem or destructive action. Harmony remains the canonical model format;
AMP, MCP, Claude Code Router, Qwen CLI, and ALMA adapters should normalize into
the same policy-enforced internal tool contract.
