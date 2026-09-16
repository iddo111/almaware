"""train.py — a real spiking neural network, trained with surrogate gradients.

Leaky-Integrate-and-Fire neurons (snnTorch), trained by backpropagation through
time with a surrogate gradient standing in for the spike's undefined derivative.
That is the standard, honest way an SNN is trained today.

Two datasets:

  mnist      the canonical SNN benchmark. Pixels become spike trains (rate or
             latency coded). Chance = 10%.
  syllables  Iddo's own 22 Hebrew syllables, heard through the SAME frozen
             cochlea ERAN wears (cochlea.py, proven bit-identical to
             eran-brain/body/ears.py). Chance = 4.545%. The 8 cochlear slices
             are 8 MOMENTS, so they can be fed as the network's own time axis —
             this is the question worth asking: does a spiking net beat the
             prototype organism on Iddo's own voice?

Writes newline-delimited JSON events as it trains (--events) so a GUI can watch
live, and one results JSON at the end (--results). Prints the chance baseline
BEFORE any number of its own, every time.

CLI:
  python train.py --dataset syllables --hidden 512 --epochs 30
"""
import argparse
import gzip
import json
import os
import signal
import sys
import time
import urllib.request

import numpy as np
import torch
import torch.nn as nn

import snntorch as snn
from snntorch import surrogate, spikegen

import cochlea

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CORPUS = os.path.join(HERE, "corpus-syllables")

MNIST_URL = "https://ossci-datasets.s3.amazonaws.com/mnist/"
MNIST_FILES = {
    "train_x": "train-images-idx3-ubyte.gz",
    "train_y": "train-labels-idx1-ubyte.gz",
    "test_x": "t10k-images-idx3-ubyte.gz",
    "test_y": "t10k-labels-idx1-ubyte.gz",
}

SURROGATES = {
    "atan": surrogate.atan,
    "sigmoid": surrogate.sigmoid,
    "fast_sigmoid": surrogate.fast_sigmoid,
    "triangular": surrogate.triangular,
    "straight_through": surrogate.straight_through_estimator,
}

# Input gain, per encoding. THIS KNOB IS NOT COSMETIC.
# A rate- or latency-coded input is already a train of unit spikes, so gain 1
# is right. The cochlear percept is not: ears.py L2-normalises the whole 192
# number utterance to length 1, so each number is about 1/sqrt(192) = 0.072.
# Fed to a threshold-1.0 neuron that leaks 10% per step, the membrane tops out
# near 0.7 and NOTHING EVER FIRES — the first run of this lab scored 2.27% on
# 22 classes (below chance) for exactly that reason, with a silent hidden
# layer. sqrt(192) = 13.86 restores unit RMS per input line. Left as a knob
# because watching the raster go from silent to seizure as you turn it is the
# single most instructive thing in this GUI.
DEFAULT_GAIN = {"rate": 1.0, "latency": 1.0,
                "cochlea-time": 13.86, "static": 13.86}

_STOP = {"now": False}


def _on_signal(signum, frame):
    # Stop is a request, not a kill: finish the step, write the partial result.
    _STOP["now"] = True


# --------------------------------------------------------------- event stream
class Events:
    """One JSONL file the GUI tails. Flushed on every write — a half-written
    line the server cannot parse is worse than a slow one."""

    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8", buffering=1) if path else None

    def __call__(self, ev, **kw):
        kw["ev"] = ev
        kw["t"] = round(time.time(), 3)
        if self.f:
            self.f.write(json.dumps(kw, ensure_ascii=False) + "\n")
            self.f.flush()

    def close(self):
        if self.f:
            self.f.close()


# ------------------------------------------------------------------- datasets
def _idx_read(path):
    with gzip.open(path, "rb") as f:
        blob = f.read()
    magic = int.from_bytes(blob[:4], "big")
    ndim = magic & 0xFF
    dims = [int.from_bytes(blob[4 + 4 * i:8 + 4 * i], "big") for i in range(ndim)]
    return np.frombuffer(blob, dtype=np.uint8, offset=4 + 4 * ndim).reshape(dims)


def load_mnist(log=print):
    """MNIST as float32 in [0,1]. Downloads once; no torchvision needed."""
    os.makedirs(DATA, exist_ok=True)
    cache = os.path.join(DATA, "mnist.npz")
    if os.path.exists(cache):
        z = np.load(cache)
        return z["xtr"], z["ytr"], z["xte"], z["yte"]
    out = {}
    for key, fn in MNIST_FILES.items():
        p = os.path.join(DATA, fn)
        if not os.path.exists(p):
            log(f"downloading {fn} ...")
            urllib.request.urlretrieve(MNIST_URL + fn, p)
        out[key] = _idx_read(p)
    xtr = (out["train_x"].reshape(-1, 784).astype(np.float32) / 255.0)
    xte = (out["test_x"].reshape(-1, 784).astype(np.float32) / 255.0)
    ytr = out["train_y"].astype(np.int64)
    yte = out["test_y"].astype(np.int64)
    np.savez_compressed(cache, xtr=xtr, ytr=ytr, xte=xte, yte=yte)
    return xtr, ytr, xte, yte


def load_syllables(log=print):
    """(N,8,24) cochlear percepts. train/ trains, heldout/ is the exam only."""
    cache = os.path.join(DATA, "syllables_cochlea.npz")
    if os.path.exists(cache):
        z = np.load(cache)
        return z["xtr"], z["ytr"], z["xte"], z["yte"]
    if not os.path.isdir(CORPUS):
        raise SystemExit(f"corpus not found: {CORPUS}")
    log("hearing the corpus through the frozen cochlea ...")
    xtr, ytr = cochlea.load_split(CORPUS, "train")
    xte, yte = cochlea.load_split(CORPUS, "heldout")
    os.makedirs(DATA, exist_ok=True)
    np.savez_compressed(cache, xtr=xtr, ytr=ytr, xte=xte, yte=yte)
    return xtr, ytr, xte, yte


# ------------------------------------------------------------------- encoding
def encode(batch, cfg, device):
    """(B, ...) -> (T, B, n_in) input current / spike train for the network."""
    enc, T = cfg["encoding"], cfg["steps"]
    g = float(cfg.get("input_gain", 1.0))
    x = batch.to(device)
    if enc == "rate":
        return spikegen.rate(x.flatten(1), num_steps=T) * g
    if enc == "latency":
        return spikegen.latency(x.flatten(1), num_steps=T,
                                normalize=True, linear=True) * g
    if enc == "static":
        return x.flatten(1).unsqueeze(0).repeat(T, 1, 1) * g
    if enc == "cochlea-time":
        # THE SPIKING ONE. x is (B, 8, 24): 8 cochlear slices = 8 moments.
        # Each slice is held as input current for steps_per_slice timesteps and
        # the membranes carry the syllable forward through time. The network
        # never sees the whole utterance at once — it has to remember it.
        per = max(1, round(T / x.shape[1]))
        return x.permute(1, 0, 2).repeat_interleave(per, dim=0) * g
    raise ValueError(f"unknown encoding {enc!r}")


def encoded_shape(cfg, sample):
    """(timesteps actually used, input width) for this dataset+encoding."""
    enc, T = cfg["encoding"], cfg["steps"]
    if enc == "cochlea-time":
        per = max(1, round(T / sample.shape[1]))
        return sample.shape[1] * per, int(sample.shape[2])
    return T, int(np.prod(sample.shape[1:]))


# -------------------------------------------------------------------- network
class SpikingNet(nn.Module):
    """Two fully-connected layers of Leaky-Integrate-and-Fire neurons.

    Every neuron holds a membrane potential that decays by `beta` each timestep,
    fires a spike when it crosses `threshold`, and resets by subtraction. The
    spike is a step function with no usable derivative, so training substitutes
    a smooth surrogate on the backward pass only — the forward pass stays
    genuinely binary. That is what makes this a spiking network and not an ANN
    with a funny activation.
    """

    def __init__(self, n_in, n_hidden, n_out, beta, threshold, spike_grad,
                 recurrent=False):
        super().__init__()
        self.recurrent = bool(recurrent)
        self.fc1 = nn.Linear(n_in, n_hidden)
        if self.recurrent:
            # The hidden layer wired back into itself. A plain LIF layer can
            # only remember through its own leak, which fades in a few steps;
            # recurrent weights let the population hold a syllable's earlier
            # slices while the later ones arrive. Matters for cochlea-time,
            # where the 8 slices ARE the signal, and barely at all for a
            # static image.
            self.lif1 = snn.RLeaky(beta=beta, threshold=threshold,
                                   spike_grad=spike_grad, linear_features=n_hidden)
        else:
            self.lif1 = snn.Leaky(beta=beta, threshold=threshold,
                                  spike_grad=spike_grad)
        self.fc2 = nn.Linear(n_hidden, n_out)
        self.lif2 = snn.Leaky(beta=beta, threshold=threshold,
                              spike_grad=spike_grad)

    def forward(self, x_seq, record=False):
        if self.recurrent:
            spk1, mem1 = self.lif1.init_rleaky()
        else:
            mem1 = self.lif1.init_leaky()
        mem2 = self.lif2.init_leaky()
        spk_out, spk_hid, mem_hid, mem_out = [], [], [], []
        fired = 0.0
        for t in range(x_seq.shape[0]):
            cur1 = self.fc1(x_seq[t])
            if self.recurrent:
                spk1, mem1 = self.lif1(cur1, spk1, mem1)
            else:
                spk1, mem1 = self.lif1(cur1, mem1)
            spk2, mem2 = self.lif2(self.fc2(spk1), mem2)
            spk_out.append(spk2)
            fired = fired + spk1.detach().mean()
            if record:
                spk_hid.append(spk1)
                mem_hid.append(mem1)
                mem_out.append(mem2)
        out = torch.stack(spk_out)
        # The hidden firing rate is the health check: 0.0 means a DEAD network
        # and any accuracy it reports is the output bias, not learning.
        self.last_hidden_rate = float(fired / max(1, x_seq.shape[0]))
        if not record:
            return out, None, None, None
        return out, torch.stack(spk_hid), torch.stack(mem_hid), torch.stack(mem_out)


# ------------------------------------------------------------------ the watch
def snapshot(net, X, y, cfg, device, classes, max_neurons=120, max_dots=5000):
    """One sample, forward with recording — this is what the GUI draws.

    Spike rasters are sent as [timestep, neuron] pairs because a raster is
    mostly empty; membrane traces are sent whole because they are not.
    """
    net.eval()
    with torch.no_grad():
        i = int(np.random.randint(len(X)))
        xb = torch.as_tensor(X[i:i + 1])
        seq = encode(xb, cfg, device)
        out, hid, memh, memo = net(seq, record=True)
        counts = out.sum(0)[0]
        pred = int(counts.argmax())

        def raster(sp, cap):
            a = sp[:, 0, :cap].detach().cpu().numpy()
            ts, ns = np.nonzero(a)
            if len(ts) > max_dots:
                keep = np.linspace(0, len(ts) - 1, max_dots).astype(int)
                ts, ns = ts[keep], ns[keep]
            return [[int(t), int(n)] for t, n in zip(ts, ns)]

        n_show = min(max_neurons, hid.shape[2])
        traces = memh[:, 0, :6].detach().cpu().numpy().T.round(4).tolist()
        return {
            "raster_hidden": raster(hid, n_show),
            "hidden_shown": n_show,
            "raster_out": raster(out, out.shape[2]),
            "n_out": int(out.shape[2]),
            "timesteps": int(out.shape[0]),
            "mem_hidden": traces,
            "mem_out": memo[:, 0, :].detach().cpu().numpy().T.round(4).tolist(),
            "threshold": cfg["threshold"],
            "spike_counts": counts.detach().cpu().numpy().astype(int).tolist(),
            "label": classes[int(y[i])],
            "pred": classes[pred],
            "correct": bool(pred == int(y[i])),
            "hidden_rate": float(hid.mean().item()),
        }


# ----------------------------------------------------------------- evaluation
@torch.no_grad()
def evaluate(net, X, y, cfg, device, batch=256, limit=None):
    net.eval()
    n = len(X) if limit is None else min(limit, len(X))
    right = 0
    for s in range(0, n, batch):
        xb = torch.as_tensor(X[s:s + batch])
        yb = torch.as_tensor(y[s:s + batch]).to(device)
        out, _, _, _ = net(encode(xb, cfg, device))
        right += int((out.sum(0).argmax(1) == yb).sum())
    return right / max(1, n)


# ----------------------------------------------------------------------- main
def run(cfg, events, log=print, data=None, install_signals=True):
    """Train once. `data` overrides the dataset's own split — that is how
    sweep.py tunes on a dev split carved out of train, so the heldout stays an
    exam and is opened exactly once, at the end, for the chosen config."""
    if install_signals:
        signal.signal(signal.SIGTERM, _on_signal)
        signal.signal(signal.SIGINT, _on_signal)
    torch.set_num_threads(int(cfg.get("threads", 4)))
    torch.manual_seed(int(cfg["seed"]))
    np.random.seed(int(cfg["seed"]))

    cuda = torch.cuda.is_available()
    device = torch.device("cuda" if cuda and cfg.get("device") != "cpu" else "cpu")

    if cfg["dataset"] == "mnist":
        xtr, ytr, xte, yte = data or load_mnist(log)
        classes = [str(i) for i in range(10)]
        chance = 0.1
        baselines = {"chance": 0.1}
    else:
        xtr, ytr, xte, yte = data or load_syllables(log)
        classes = cochlea.CLASSES
        chance = cochlea.CHANCE
        baselines = dict(cochlea.BASELINES, **cochlea.ORGANISM)

    # THE CHANCE LINE FIRST — before any number of our own. House rule.
    log(f"chance = {chance:.4%}  ({len(classes)} classes)")
    for k, v in sorted(baselines.items(), key=lambda kv: kv[1]):
        log(f"  baseline {k:38s} {v:.4%}")

    T, n_in = encoded_shape(cfg, xtr)
    net = SpikingNet(n_in, cfg["hidden"], len(classes), cfg["beta"],
                     cfg["threshold"], SURROGATES[cfg["surrogate"]](),
                     recurrent=bool(cfg.get("recurrent"))).to(device)
    n_params = sum(p.numel() for p in net.parameters())
    opt = torch.optim.Adam(net.parameters(), lr=cfg["lr"], betas=(0.9, 0.999))
    loss_fn = nn.CrossEntropyLoss()

    # Where the tensors REALLY are — asked, not assumed.
    probe = encode(torch.as_tensor(xtr[:2]), cfg, device)
    log(f"torch {torch.__version__} | cuda_available={cuda} | "
        f"device={device} | input tensor on {probe.device} | "
        f"weights on {next(net.parameters()).device}")
    log(f"net {n_in} -> {cfg['hidden']} LIF -> {len(classes)} LIF | "
        f"{n_params:,} params | {T} timesteps | encoding={cfg['encoding']}")

    events("start", cfg=cfg, chance=chance, baselines=baselines,
           classes=classes, n_train=len(xtr), n_test=len(xte),
           timesteps=T, n_in=n_in, n_params=n_params,
           device=str(device), cuda_available=cuda,
           tensor_device=str(probe.device), torch=torch.__version__,
           gpu=(torch.cuda.get_device_name(0) if cuda else None))

    t0 = time.time()
    best, hist, step = 0.0, [], 0
    stopped = False
    order = np.arange(len(xtr))
    B = int(cfg["batch"])
    for epoch in range(int(cfg["epochs"])):
        net.train()
        np.random.shuffle(order)
        run_loss, nb, rate = 0.0, 0, 0.0
        for s in range(0, len(order), B):
            if _STOP["now"]:
                stopped = True
                break
            idx = order[s:s + B]
            xb = torch.as_tensor(xtr[idx])
            yb = torch.as_tensor(ytr[idx]).to(device)
            seq = encode(xb, cfg, device)
            out, _, _, _ = net(seq)
            # Loss at EVERY timestep: the network is pushed to be right the
            # whole time it is spiking, not only at the end (ce_rate_loss).
            loss = sum(loss_fn(out[t], yb) for t in range(out.shape[0])) / out.shape[0]
            opt.zero_grad()
            loss.backward()
            opt.step()
            run_loss += float(loss.detach())
            rate = net.last_hidden_rate
            nb += 1
            step += 1
            if step % int(cfg["log_every"]) == 0:
                events("step", epoch=epoch, step=step,
                       loss=round(float(loss.detach()), 5),
                       hidden_rate=round(rate, 5),
                       train_batch_acc=round(float((out.sum(0).argmax(1) == yb)
                                                   .float().mean()), 4))
        if stopped:
            break
        tr_acc = evaluate(net, xtr, ytr, cfg, device, limit=int(cfg["eval_train_n"]))
        te_acc = evaluate(net, xte, yte, cfg, device)
        best = max(best, te_acc)
        hist.append({"epoch": epoch, "loss": run_loss / max(1, nb),
                     "train_acc": tr_acc, "test_acc": te_acc})
        log(f"epoch {epoch + 1}/{cfg['epochs']}  loss {run_loss / max(1, nb):.4f}  "
            f"train {tr_acc:.2%}  test {te_acc:.2%}  "
            f"(chance {chance:.2%})  spikes/neuron/step {rate:.3f}  "
            f"{time.time() - t0:.0f}s")
        events("epoch", epoch=epoch, loss=round(run_loss / max(1, nb), 5),
               train_acc=round(tr_acc, 5), test_acc=round(te_acc, 5),
               best=round(best, 5), hidden_rate=round(rate, 5),
               elapsed=round(time.time() - t0, 1))
        events("viz", **snapshot(net, xte, yte, cfg, device, classes))

    wall = time.time() - t0
    final = hist[-1]["test_acc"] if hist else 0.0
    res = {
        "run_id": cfg["run_id"], "cfg": cfg, "stopped": stopped,
        "chance": chance, "baselines": baselines,
        "final_test_acc": final, "best_test_acc": best,
        "epochs_done": len(hist), "wall_seconds": round(wall, 1),
        "device": str(device), "cuda_available": cuda,
        "tensor_device": str(probe.device),
        "gpu": (torch.cuda.get_device_name(0) if cuda else None),
        "n_params": n_params, "timesteps": T, "n_in": n_in,
        "hidden_rate": round(rate, 5) if hist else None,
        "n_train": len(xtr), "n_test": len(xte),
        "history": hist,
        "beats_chance": bool(final > chance),
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if cfg["dataset"] == "syllables":
        org = cochlea.ORGANISM["prototype_organism_heldout"]
        res["vs_prototype_organism"] = round(final - org, 5)
        res["beats_prototype_organism"] = bool(final > org)
    if cfg.get("results"):
        os.makedirs(os.path.dirname(cfg["results"]), exist_ok=True)
        with open(cfg["results"], "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
    log(f"DONE  final test {final:.2%}  best {best:.2%}  "
        f"chance {chance:.2%}  {wall:.0f}s  device={device}"
        + ("  [STOPPED EARLY]" if stopped else ""))
    events("done", **{k: v for k, v in res.items() if k != "history"})
    return res


def parse(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", choices=["mnist", "syllables"], default="syllables")
    p.add_argument("--encoding", default=None,
                   help="mnist: rate|latency|static ; syllables: cochlea-time|static")
    p.add_argument("--hidden", type=int, default=512)
    p.add_argument("--beta", type=float, default=0.9, help="membrane decay 0..1")
    p.add_argument("--threshold", type=float, default=1.0)
    p.add_argument("--surrogate", choices=sorted(SURROGATES), default="atan")
    p.add_argument("--lr", type=float, default=5e-4)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--epochs", type=int, default=20)
    p.add_argument("--steps", type=int, default=32, help="timesteps per sample")
    p.add_argument("--input-gain", type=float, default=None, dest="input_gain",
                   help="scales the input current. Too low = silent network.")
    p.add_argument("--recurrent", action="store_true",
                   help="hidden layer wired back to itself (snn.RLeaky)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--device", default="auto")
    p.add_argument("--log-every", type=int, default=10, dest="log_every")
    p.add_argument("--eval-train-n", type=int, default=2000, dest="eval_train_n")
    p.add_argument("--run-id", default=None, dest="run_id")
    p.add_argument("--events", default=None)
    p.add_argument("--results", default=None)
    a = p.parse_args(argv)
    cfg = vars(a)
    if not cfg["encoding"]:
        cfg["encoding"] = "rate" if cfg["dataset"] == "mnist" else "cochlea-time"
    if cfg["input_gain"] is None:
        cfg["input_gain"] = DEFAULT_GAIN.get(cfg["encoding"], 1.0)
    if not cfg["run_id"]:
        cfg["run_id"] = f"{cfg['dataset']}-{time.strftime('%Y%m%d-%H%M%S')}"
    return cfg


def main(argv=None):
    cfg = parse(argv)
    events = Events(cfg.get("events"))

    def log(*a):
        print(*a, flush=True)
        events("log", msg=" ".join(str(x) for x in a))
    try:
        run(cfg, events, log)
    except Exception as e:                                   # noqa: BLE001
        events("error", msg=f"{type(e).__name__}: {e}")
        raise
    finally:
        events.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
