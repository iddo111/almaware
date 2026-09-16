"""THE GUARDS THIS CHAIN DID NOT HAVE — one place for the refusals.

> BROKEN WINDOWS LAW: if it's not working, fix it IMMEDIATELY. Test the REAL output.

Written 2026-09-06 during the code revision Iddo ordered ("תעשה לכל המודלים AI שלנו קוד
רוויזן... שכל שרשרת האכלה אימון הרצה שלהם תקינה"). Three things this holobrain chain
kept doing, each of which cost a run or a claim:

  * It loaded a frozen encoder into a model of a different shape and let torch report a
    bare `size mismatch for proj.weight`. eye.pt is a GRAYSCALE encoder; the corpus went
    to 3-channel colour on 2026-08-31 and the eye was never retrained. Both entry points
    have been dead on arrival for six days and NOTHING SAID SO. `check_eye_checkpoint`
    names both files, both mtimes and both shapes, and refuses.

  * It printed "the eye encoder AND the binding never saw them" about a checkpoint that
    records no holdout at all — eye.py's `--holdout` defaults to 0 and eye.pt stores no
    args. `encoder_holdout` returns None so the caller has to say UNKNOWN out loud.

  * It ran on the PC. nezer.py already refuses by hostname, with the incident written at
    the site: "they ran eye.py and zivug.py locally, took the machine to 100% CPU while
    Iddo was working, and I had to kill them twice." The two scripts nezer COPIES did not
    carry the guard nezer was given. `refuse_on_pc` is that guard, lifted out.

Nothing here trains, loads a model, or touches the network. Stdlib + numpy + torch.load.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import platform

import numpy as np

# Boxes this chain is allowed to train on, copied from nezer.py:158 so the two cannot
# drift apart. eran1 is DELIBERATELY ABSENT and stays absent: the organism lives there
# and it serves Iddo's mic. The PC is not on the list either, and that is the point.
FLEET = ("eran2", "eran3", "eran4",
         "edgexpert-041d",     # eran2 — the senses
         "edgexpert-01e6",     # eran3 — mostly idle; the shoot's intended soil
         "edgexpert-3636")     # eran4 — Darwish + audio


class Refused(RuntimeError):
    """A guard said no. Loud on purpose: this is the failure that used to be silent."""


def iso(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def mtime(path: str) -> str:
    try:
        return iso(os.stat(path).st_mtime)
    except OSError:
        return "missing"


def npz_shape(path: str, key: str):
    """The shape of one array in an .npz WITHOUT decompressing it.

    The guard runs before the corpus is loaded for real, and reading 40 MB twice to
    answer a question about a header is the kind of cost that gets a check deleted.
    """
    try:
        import zipfile

        import numpy.lib.format as nf
        with zipfile.ZipFile(path) as z:
            name = key + ".npy"
            if name not in z.namelist():
                return None
            with z.open(name) as f:
                ver = nf.read_magic(f)
                shape, _, _ = nf._read_array_header(f, ver)
                return tuple(int(x) for x in shape)
    except Exception:                                                # noqa: BLE001
        try:
            with np.load(path, allow_pickle=True) as d:
                return tuple(int(x) for x in d[key].shape)
        except Exception:                                            # noqa: BLE001
            return None


def fingerprint(path: str, key: str = None) -> dict:
    """Enough to tell whether the file a checkpoint was trained on is the file on disk.

    Size + sha256 of the first megabyte + the array shape. NOT mtime: a fleet copy has a
    different mtime and the same content, and refusing that would train nobody.
    """
    st = os.stat(path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read(1024 * 1024))
    shape = npz_shape(path, key) if key else None
    return {"file": os.path.basename(path), "bytes": int(st.st_size),
            "mtime": iso(st.st_mtime), "sha256_first_mb": h.hexdigest(),
            "shape": list(shape) if shape else None}


def same_corpus(a, b) -> bool:
    """Two fingerprints of the same bytes. mtime is ignored; content is not."""
    if not a or not b:
        return False
    return all(a.get(k) == b.get(k) for k in ("bytes", "sha256_first_mb", "shape"))


def check_eye_checkpoint(eye_path: str, letters_path: str, patch: int, ch: int,
                         torch=None):
    """Refuse before `load_state_dict` turns a stale encoder into a traceback.

    Returns the loaded checkpoint dict so the caller does not read it twice.
    """
    if torch is None:
        import torch                                                 # noqa: PLC0415
    if not os.path.exists(eye_path):
        raise Refused("the eye's checkpoint is missing: %s" % eye_path)
    ck = torch.load(eye_path, map_location="cpu")
    w = (ck.get("encoder") or {}).get("proj.weight")
    if w is None:
        raise Refused("%s (mtime %s) has no encoder.proj.weight -- it is not an eye "
                      "checkpoint." % (eye_path, mtime(eye_path)))
    have, want = int(w.shape[1]), patch * patch * ch
    shape = npz_shape(letters_path, "X")
    if have != want:
        raise Refused(
            "THE EYE AND THE CORPUS ARE FROM DIFFERENT DAYS -- refusing before the "
            "traceback.\n"
            "  %s\n      mtime %s   encoder.proj.weight in-features %d "
            "(= patch %d x patch %d x %d channel(s))\n"
            "  %s\n      mtime %s   X shape %s\n"
            "  eye.py today: PATCH=%d CH=%d -> the encoder must take %d.\n"
            "  The corpus went to colour on 2026-08-31 and the encoder was never "
            "retrained, so this chain has been unrunnable ever since and said nothing.\n"
            "  FIX: retrain the eye ON THE FLEET (never the PC, never eran1) against "
            "this corpus, with an explicit --holdout, and write the holdout and the "
            "corpus fingerprint into the checkpoint. Do NOT pass strict=False: that "
            "hands the run a RANDOM projection and a plausible number."
            % (eye_path, mtime(eye_path), have, patch, patch,
               max(have // (patch * patch), 0),
               letters_path, mtime(letters_path), shape, patch, ch, want))
    if shape is not None:
        got_ch = shape[-1] if len(shape) == 4 else 1
        if got_ch != ch:
            raise Refused(
                "the corpus has %d channel(s) and eye.py expects CH=%d.\n"
                "  %s  mtime %s  X shape %s"
                % (got_ch, ch, letters_path, mtime(letters_path), shape))
    return ck


def encoder_holdout(ck: dict):
    """How many typefaces the ENCODER was held out from, or None when it does not say.

    None is the honest answer for every eye.pt written before today: eye.py's --holdout
    defaults to 0 (trains on ALL faces) and the checkpoint stored only
    encoder/gist_dim/size/patch/note. "The eye encoder never saw them" was printed
    unconditionally against exactly that.
    """
    for k in ("holdout", "holdout_fonts"):
        if isinstance(ck.get(k), int):
            return int(ck[k])
    args = ck.get("args")
    if isinstance(args, dict) and isinstance(args.get("holdout"), int):
        return int(args["holdout"])
    return None


def ink_to_eye(sheet, ch: int):
    """A drawn sheet (B,H,W) into something a CH-channel eye can actually look at.

    ZIV-16 — found on 2026-09-06 by running the chain in a fixture instead of reading it.
    ZIV-01 (a grayscale eye.pt against a colour corpus) is only HALF the colour break:
    `hand_eye.ink()` returns one channel (`.view(b, size, size)`), and `Encoder.patchify`
    permutes FOUR dimensions, so `enc.gist(ink(...))` dies with

        RuntimeError: permute(sparse_coo): ... input.dim() = 3 is not equal to len(dims) = 4

    on WINSTON's leg in zivug.py and on `read_back` / `train_scribe` in close_loop.py.
    Retraining the eye would NOT have fixed this: the shape mismatch is between the hand
    and the eye, not between the eye and its checkpoint. It has been broken since
    2026-08-31 and nothing said so, because the chain never got this far.

    The hand draws with one nib, so a drawing enters the colour space as the same ink
    coverage on every channel — a black drawing, which is the first entry in the corpus's
    own ink list ("ink black"). If the hand is ever given colour, this is the seam.
    """
    if sheet.dim() == 4:
        return sheet
    if sheet.dim() != 3:
        raise Refused("a drawn sheet should be (B,H,W); got %r" % (tuple(sheet.shape),))
    if ch == 1:
        return sheet.unsqueeze(-1)
    return sheet.unsqueeze(-1).expand(-1, -1, -1, ch)


def refuse_on_pc(override: bool = False, what: str = "this run") -> str:
    """No training on the PC. By hostname, rather than by trusting anyone to remember.

    Returns the hostname. `override` is the deliberate escape hatch and it prints, so a
    PC run is at least on the record.
    """
    host = platform.node()
    short = host.split(".")[0].lower()
    if any(short == f or short.startswith(f) for f in FLEET):
        return host
    if override:
        print("!! %s is running on %s, which is NOT a fleet box, because "
              "--i-know-this-is-the-PC was passed. Keep it short and keep it nice."
              % (what, host))
        return host
    raise Refused(
        "REFUSED: %s wants to train, and this box (%s) is not on the fleet.\n"
        "  No AI training on the PC -- it is a standing law of this workspace, and it "
        "was broken on 2026-08-31 by agents running eye.py and zivug.py here: 100%% CPU "
        "while Iddo was working, killed twice.\n"
        "  Allowed: %s   (eran1 is deliberately absent -- the organism lives there and "
        "it serves his mic.)\n"
        "  Pass --i-know-this-is-the-PC only for a few-second smoke test."
        % (what, host, ", ".join(FLEET)))
