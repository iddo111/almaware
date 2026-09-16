> 🪟 BROKEN WINDOWS LAW: if it's not working, fix it immediately. Test the REAL output, not a proxy.

# KOF headless -- the ping-pong coder that builds KESHEV 7

Iddo, 2026-09-15 03:19-03:22: *"put a chat on the mic from the start ... make us KESHEV 7, pure coding, 100% ours, no external source, no open source"* and *"write the KOF ping-pong coder and put it with Chat non-stop to do the mic from scratch ... that will be the test of the KOF coder."*

A brain (gpt-oss-120b) is put in a non-stop ping-pong loop with a runner. The brain replies with shell commands and file writes; the runner executes them inside a locked-down sandbox on eran1, feeds the output back, and never stops. The task it is given is to build **KESHEV 7** -- Iddo's Hebrew dictation mic -- from random-init models on his own ~2 h of voice, with no speech libraries and no pretrained weights. This is both the deliverable and the test of the coder.

## What "no open source" means here (state it so Iddo can tighten it)
- **Allowed:** bash, Python 3.12 stdlib, numpy, torch (tensor math), scipy, a C compiler for our own C. All already on eran1.
- **Forbidden:** any pretrained model/weights; any speech/ASR/audio-ML library or code; any git clone; any pip/conda/apt install or download; ready-made CER/WER libraries. Every model trained from random init on Iddo's data. Enforced in the runner and in a runtime import wall, not by trusting the prompt.

## Files (source of truth = D:/CLAUDE/kof/headless/)
- `kof_headless.py` -- rally engine (extends kof.py's parse/rally, no tkinter), guard, executor, seal, brain, eval driver, autosave, CLI.
- `site/sitecustomize.py` -- runtime import wall (stdlib + numpy + torch + scipy + sandbox files only).
- `eval/eval.py` -- our own Hebrew-normalized CER/WER + baselines. Lives in `~/keshev7-eval`, read-only to the rally.
- `make_split.py` -- builds train (`~/keshev7/data/train`) and held-out (`~/keshev7-eval`) from the corpus, split by session.
- `GOAL.md` -- the goal handed to the brain (Hebrew + English), with `{{...}}` filled from the real numbers at runtime.
- `keshev7-kof.service` -- USER systemd unit, Restart=always, Nice=19 (WRITTEN, NOT started).
- `config.json` -- all limits and endpoints. `test_kof_headless.py` -- full test suite (fake brain, real scopes, decoys).
- `deploy.sh` -- copy to eran1, build the split, seal, install the unit (not start).

## Host: eran1 (measured 2026-09-15)
104 GiB RAM available, no swap pressure (eran2 was already swapping). Router live: `POST http://<tailnet-ip>:8010/v1/chat/completions model gpt-oss-120b` -> PONG. n_ctx 65536.

## The guarantees, proven on decoys (test_kof_headless.py, run on eran1)
- Every deny rule blocks its decoy; normal build commands run. Memory cap (MemoryMax + MemorySwapMax=0) kills a 900 MB alloc; per-command timeout kills a sleep; disk cap kills a filler then refuses (but a cleanup `rm` still runs); mem floor refuses. STOP file halts at the next step and kills a running command. Crash mid-round: a fresh instance resumes the same round counter. Eval dir is unwritable to the rally; a chmod-and-restore is caught by the ctime seal and HALTS. `DONE` without passing the bar does not stop; a cheating transcribe.py is visible against the empty/most-frequent-word baselines. The runtime import wall blocks `transformers`/`requests`/`torchaudio` even when the name is built by string concatenation.

## Honest limits (Five Laws #5 -- say what's broken first)
- **Not kernel isolation.** eran1 blocks unprivileged user namespaces (AppArmor `apparmor_restrict_unprivileged_userns=1`) and ignores `IPAddressDeny`/`PrivateNetwork` in `--user` scopes (measured). So there is no private network/mount/pid namespace: network denial is by env proxies + text/AST guard + no net tools, not a firewall, and the import wall is skippable by `python -I` (which the guard refuses) but is not a sandbox boundary. A determined adversary running as `eran1` could get past text rules. The real fix is a dedicated unix user for the rally -- needs Iddo + sudo. For an LLM building an ASR model this guard is appropriate; it is not a jail for hostile code.
- **GPU is OFF by default** (`gpu:off`): eran1's GPU is ~81% used by Iddo's live jobs. CPU-only training of ~2 h of audio is slow. Turning `gpu:on` is Iddo's knowing call.
- **Data is ~2.0 h, frozen since 2026-09-03** (KESHEV 6's collector is wired but disabled). A CER <= 0.25 Hebrew ASR from two hours, from scratch, is genuinely hard; the loop may plateau above the bar. That is information, not failure -- the scoreboard will show it.
- **RAMCHAT posting from eran1 is off** (`ramchat_url` empty): the PC door :8876 is not on the tailnet. Posting is skipped, never fails the loop. PROGRESS.md on eran1 is the live record.

## Run (after `deploy.sh`)
```
ssh eran1
cd ~/keshev7-kof
PYTHONIOENCODING=utf-8 python3 -m unittest -v test_kof_headless   # prove it
python3 kof_headless.py verify-seal
python3 kof_headless.py steps 3      # 3 real rounds, watch it
# Iddo's go for non-stop:
systemctl --user start keshev7-kof   # stop: touch ~/keshev7/STOP  or  systemctl --user stop keshev7-kof
```
`python3 kof_headless.py status` shows round, last CER, accepted count, halted. After any change to eval/runner/site, `python3 kof_headless.py reseal`.
