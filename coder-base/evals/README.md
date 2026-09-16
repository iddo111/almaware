# Coder-model capstone evals

> 🪟 Broken Windows Law: test the REAL output, not a proxy. Every check in
> this directory either runs real code (the ALMA suite executes submissions
> through the actual `alma.Loom`) or is an explicitly-labeled, disclosed
> keyword/structural proxy (the A70 suite) — nothing here grades on vibes.

Two independent eval suites for the electronics/embedded/bare-metal-Linux
coder model (RAMCHAT `claude-cli-CODER` track, 2026-09-04). Authoring only —
building these did not touch a GPU, start a server, or train anything.

```
evals/
  a70/    Capstone 1 — bare-metal Linux on Iddo's Samsung Galaxy A70
  alma/   Capstone 2 — write a neural network in Iddo's ALMA language
```

## Capstone 1 — `a70/`

- `FINDINGS.md` — the verified hardware (Snapdragon 675 / SM6150, Kryo 460,
  Adreno 612, UFS 2.1, X12 modem) and the honest mainline/postmarketOS
  status (the device's own postmarketOS wiki entry says "not booting";
  there is no upstream device tree for this phone, though the SM6150
  *platform* has thin, recent, real upstream precedent). Read this first —
  it says plainly what is and is not achievable, and names the one fact
  (which exact SM-A705 region variant Iddo's physical phone is) that has
  to be checked on the device itself before anything else, because an
  SM-A705U cannot have its bootloader unlocked at all.
- `tasks/01`–`06` — six graded tasks: identify the hardware, explain the
  boot chain, write a device-tree UART node, write a minimal defconfig,
  write postmarketOS packaging, and diagnose a boot hang from a log. Each
  task file states the exact prompt to give the model, the grading
  rubric, and an honesty note about how strong or weak that particular
  check is (several are keyword/structural proxies for a real compile —
  this machine has no `dtc` and no kernel tree, both disclosed).
- `sample_logs/boot_hang.log` — the synthetic (but realistic — every log
  string is a real Linux kernel message, cited in the task file) boot log
  for Task 6.
- `grader.py` — run it:
  ```
  PYTHONIOENCODING=utf-8 python grader.py identify   answer.txt
  PYTHONIOENCODING=utf-8 python grader.py bootchain  answer.txt
  PYTHONIOENCODING=utf-8 python grader.py devicetree answer.dts
  PYTHONIOENCODING=utf-8 python grader.py defconfig  answer.txt
  PYTHONIOENCODING=utf-8 python grader.py pmaports   answer.txt
  PYTHONIOENCODING=utf-8 python grader.py diagnose   answer.txt
  PYTHONIOENCODING=utf-8 python grader.py self_test   # proves the checks aren't vacuous
  ```
  `self_test` runs a hand-written strong answer and a hand-written weak
  answer through every mode and asserts the strong one passes and the weak
  one fails — run this once after touching the grader to prove it still
  discriminates.

## Capstone 2 — `alma/`

- `FINDINGS.md` — the honest capability assessment: **ALMA can express a
  real feed-forward neural network's inference today** (a verified 2-ReLU-
  hidden-unit MLP solving XOR runs on the real, unmodified loom — see
  `reference_solutions/L5.json`), **but cannot express training it**
  (no backprop, no gradient, no tensors — `drift` is the only weight-
  adjustment mechanism, and it is a local, forward-only rule, not an error
  signal). Also reports SPEC.md's real size (~5,000 tokens, tiktoken-
  measured, GPT-family-tokenizer estimate since no local Qwen tokenizer was
  found to measure exactly) and which ALMA source files are in the
  project's `sha1(relpath) % 20 == 7` hold-out set.
- `tasks/L0`–`L5` — a graded ladder from a trivial single-knot linear
  function up to the capstone MLP, each with an exact contract (which knot
  names carry inputs/outputs) so grading needs zero human judgment.
- `grader.py` — loads a submitted `.json` or `.voice` weave with the real
  `alma` package (`D:\CLAUDE\alma-language`) and **runs it** through
  `alma.Loom`, comparing the recorded output against an independently
  computed expected value for several test inputs per task:
  ```
  PYTHONIOENCODING=utf-8 python grader.py L0 submission.json
  PYTHONIOENCODING=utf-8 python grader.py L1 submission.json
  PYTHONIOENCODING=utf-8 python grader.py L2 submission.json
  PYTHONIOENCODING=utf-8 python grader.py L3 submission.json
  PYTHONIOENCODING=utf-8 python grader.py L4 submission.json
  PYTHONIOENCODING=utf-8 python grader.py L5 submission.json
  PYTHONIOENCODING=utf-8 python grader.py all reference_solutions/   # self-test, all 6 pass
  ```
- `reference_solutions/` — one verified, working weave per task (proof the
  ladder is solvable, and a regression fixture for the grader itself), plus
  `negative_examples/` — two deliberately wrong submissions that the
  grader must reject (a `spell="xor"` cheat, and a wrong-bias perceptron)
  to prove the checks actually discriminate rather than rubber-stamping.

## How to actually run either suite against a model

Neither suite depends on the other, and neither needs a GPU:

1. Give the model the task prompt from the relevant `tasks/*.md` file
   (for `alma/`, also put the real `SPEC.md` — `D:\CLAUDE\alma-language\
   SPEC.md` — in context first, per the approved plan: try in-context
   before training anything).
2. Save its answer to a text file (or `.json`/`.voice` for the ALMA tasks,
   `.dts` for A70 Task 3).
3. Run the matching `grader.py` command above.
4. For `alma/`, a PASS means the real loom produced the exact right numbers
   on every test case — there is nothing else to check by hand. For `a70/`,
   a PASS on the keyword/structural checks is necessary but not sufficient
   proof of a correct real-world answer for tasks 2–6 (see each task's
   honesty note); treat those as a fast automatic filter, not a final
   verdict, until someone with a kernel tree and `dtc` re-checks a
   promising answer for real.

## What this pair of suites does and does not tell you

- It tells you, mechanically, whether a model can compose ALMA's existing
  primitives into a real small neural network, and whether it knows the
  *specific*, *real*, *citable* facts about this *specific* phone's SoC,
  mainline status, and boot chain — not generic "Linux on ARM" trivia.
- It does **not** tell you whether the model can actually get a Galaxy A70
  booting mainline Linux (nobody has done that yet, per `a70/FINDINGS.md`)
  or whether ALMA can be *trained*, not just hand-wired, into a working
  network (it structurally cannot, today, per `alma/FINDINGS.md`). Both
  suites say so themselves, on purpose — an eval that oversold either
  capstone would be worse than no eval at all.
