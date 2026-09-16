# -*- coding: utf-8 -*-
"""KESHEV 7 runtime wall -- loaded by every python a rally command starts.

The runner (kof_headless.py) puts this directory first on PYTHONPATH and sets
KESHEV7_SANDBOX. Two walls are installed:

  1. IMPORT WALL: code in the sandbox (or from -c / stdin) may import ONLY the
     python standard library, numpy, torch, scipy, and the sandbox's own
     modules. Speech / pretrained-model packages are refused for everyone.

  2. FILE JAIL (sys.addaudithook on the "open" event and the write/rename/
     unlink events): python opened here may WRITE only inside the sandbox and
     may READ only the sandbox, the python installation / site-packages, and a
     tiny system allow-list. This holds no matter how the path string is built
     (chr(), concatenation, os.sep.join) because the hook sees the resolved
     path at the moment of the syscall -- closing the "python -c
     open(chr(47)+...)" arbitrary read/write and the read into ~/keshev7-eval.

This is a wall against shortcuts and same-language tricks, not a kernel
boundary: a COMPILED binary or a non-python interpreter honours neither wall
(the runner denies those separately), and python -I / -E / -S would skip
sitecustomize (the runner's guard refuses those). Iddo's order 2026-09-15:
"100% ours, no external source, no open source".
"""
import os
import sys

_SANDBOX = os.environ.get("KESHEV7_SANDBOX", "")

_ALLOWED_THIRD_PARTY = {"numpy", "torch", "scipy"}

_BLOCKED = {
    # speech / ASR / audio-ML code
    "whisper", "faster_whisper", "ctranslate2", "vosk", "kaldi", "kaldiio",
    "kaldifeat", "espnet", "espnet2", "speechbrain", "nemo", "nemo_toolkit",
    "silero", "silero_vad", "deepspeech", "pocketsphinx", "sphinxbase",
    "librosa", "python_speech_features", "lhotse", "icefall", "k2", "kenlm",
    "pyctcdecode", "funasr", "pyannote", "torchaudio", "webrtcvad",
    "audiomentations", "soundfile", "pydub", "sounddevice", "pyaudio",
    # pretrained-model / tokenizer / hub code
    "transformers", "tokenizers", "sentencepiece", "tiktoken", "datasets",
    "accelerate", "safetensors", "fastsafetensors", "huggingface_hub",
    "openai", "openai_harmony", "onnx", "onnxruntime", "tensorflow", "keras",
    "jax", "flax", "timm", "torchvision",
    # ready-made metrics and network clients
    "jiwer", "editdistance", "Levenshtein", "rapidfuzz", "requests",
    "urllib3", "httpx", "aiohttp", "paramiko",
}


def _msg(name):
    return ("KESHEV7 GUARD: import '%s' is refused - KESHEV 7 is 100%% ours: "
            "only the python stdlib, numpy, torch, scipy and your own files "
            "in the sandbox. Write it yourself." % name)


if _SANDBOX:
    _SANDBOX = os.path.realpath(_SANDBOX)
    _PREFIX = _SANDBOX.rstrip(os.sep) + os.sep
    _STDLIB = set(getattr(sys, "stdlib_module_names", ())) | set(
        sys.builtin_module_names)
    _HERE = os.path.abspath(__file__)

    def _in_sandbox(path):
        try:
            return os.path.realpath(path).startswith(_PREFIX)
        except Exception:
            return False

    # ---- import wall --------------------------------------------------------
    # SPEC PROBES (2026-09-15). importlib.util.find_spec(name) only ASKS "is it
    # there?" and loads nothing; torch probes 'onnx', 'tensorflow', ... that way
    # (torch/_dynamo/trace_rules.py add()) whenever torch.optim builds an
    # optimizer. A meta_path finder that raises there crashes the library, so a
    # probe of a refused name is answered "not available": the wall returns
    # None and marks the refusal, and the find_spec filter below turns the
    # whole probe into None - even when the package IS installed and a later
    # finder would have handed back its spec. A real import statement,
    # importlib.import_module or __import__ still raises the guard.
    # Detection, measured on eran1 python 3.12: the finder's caller is
    # importlib._bootstrap._find_spec and ITS caller is the genuine
    # importlib.util.find_spec code object. Every real import (including the
    # parent import a dotted probe makes) has _find_and_load_unlocked there.
    import importlib.util as _ilu
    import threading as _probe_threading
    _PROBE_CODE = _ilu.find_spec.__code__
    _ORIG_FIND_SPEC = _ilu.find_spec
    _probe_state = _probe_threading.local()

    def _is_probe(frame):
        try:
            return (frame.f_code.co_name == "_find_spec"
                    and frame.f_back is not None
                    and frame.f_back.f_code is _PROBE_CODE)
        except Exception:
            return False

    def _refuse_probe(name):
        _probe_state.refused = name
        return None

    def _find_spec_probe(name, package=None):
        prev = getattr(_probe_state, "refused", None)
        _probe_state.refused = None
        try:
            spec = _ORIG_FIND_SPEC(name, package)
            refused = _probe_state.refused
        finally:
            _probe_state.refused = prev
        if refused is not None:
            full = (_ilu.resolve_name(name, package) if name.startswith(".")
                    else name)
            if refused == full:
                return None
        return spec

    for _a in ("__module__", "__name__", "__qualname__", "__doc__"):
        try:
            setattr(_find_spec_probe, _a, getattr(_ORIG_FIND_SPEC, _a))
        except Exception:
            pass
    _ilu.find_spec = _find_spec_probe

    # ---- caller classification ---------------------------------------------
    # importlib.import_module / pkgutil.find_loader / runpy.run_module all reach
    # a meta_path finder ON BEHALF OF whoever called THEM: their own frames
    # (importlib/*, pkgutil.py, runpy.py) sit between the sandbox and this wall.
    # The old caller walk stopped at the first of those real stdlib files and
    # read the request as "a library's own import", so importlib.import_module(
    # "<installed pkg>") and pkgutil.find_loader(name).load_module() from sandbox
    # code loaded the package. The walk below sees PAST import machinery to the
    # frame that really asked, and decides by that: sandbox -> refuse; a genuine
    # library (numpy/torch/scipy site-packages) doing its own import -> allow.
    _MACHINERY_FILES = set()
    _MACHINERY_DIRS = set()
    try:
        _MACHINERY_DIRS.add(os.path.realpath(os.path.dirname(_ilu.__file__)))
    except Exception:
        pass
    for _mmod in ("pkgutil", "runpy"):
        try:
            _m = __import__(_mmod)
            if getattr(_m, "__file__", None):
                _MACHINERY_FILES.add(os.path.realpath(_m.__file__))
        except Exception:
            pass

    def _frame_kind(fn):
        """Classify a frame's file. 'frozen'/'machinery'/'here' are transparent
        (a request only passes THROUGH them); 'sandbox' means the request came
        from sandbox code (or -c / stdin, spelled <string>/<stdin>); 'library'
        is the stdlib or site-packages (numpy/torch/scipy and friends)."""
        if fn.startswith("<frozen"):
            return "frozen"
        try:
            if os.path.abspath(fn) == _HERE:
                return "here"
        except Exception:
            pass
        if fn.startswith("<"):
            return "sandbox"          # <string>, <stdin>: a sandbox -c / heredoc
        try:
            rp = os.path.realpath(fn)
        except Exception:
            return "library"
        if rp in _MACHINERY_FILES:
            return "machinery"
        for d in _MACHINERY_DIRS:
            if rp == d or rp.startswith(d + os.sep):
                return "machinery"
        if rp.startswith(_PREFIX) or rp == _SANDBOX:
            return "sandbox"
        return "library"

    def _requester_is_sandbox(depth):
        """Walk callers from `depth` past import machinery to the first frame
        that really asked. True if that frame is sandbox code (or the stack ran
        out, treated as sandbox = refuse)."""
        try:
            f = sys._getframe(depth)
        except ValueError:
            return True
        while f is not None:
            k = _frame_kind(f.f_code.co_filename)
            if k in ("frozen", "machinery", "here"):
                f = f.f_back
                continue
            return k == "sandbox"
        return True

    def _probe_caller_is_direct_sandbox():
        """For a probe (a call that arrived through importlib.util.find_spec):
        is the frame that CALLED find_spec sandbox code? A direct sandbox probe
        (importlib.util.find_spec('x')) must get a graceful None so find_spec
        never raises; a probe issued BY machinery (pkgutil.find_loader) on
        behalf of sandbox code is a disguised load and must raise. Measured on
        eran1 python 3.12: runpy is a FROZEN module (<frozen runpy> frames), so
        runpy.run_module's probe reads as direct and gets the graceful None -
        runpy then raises 'No module named ...' and nothing is loaded."""
        f = sys._getframe(1)
        while f is not None:
            if (f.f_code.co_name == "_find_spec" and f.f_back is not None
                    and f.f_back.f_code is _PROBE_CODE):
                g = f.f_back.f_back      # caller of importlib.util.find_spec
                while g is not None:     # (our own _find_spec_probe is 'here')
                    k = _frame_kind(g.f_code.co_filename)
                    if k in ("frozen", "here"):
                        g = g.f_back
                        continue
                    return k == "sandbox"
                return True
            f = f.f_back
        return False

    class _KeshevImportWall(object):
        def find_spec(self, name, path=None, target=None):
            top = name.partition(".")[0]
            if top in _BLOCKED:
                if _is_probe(sys._getframe(1)):
                    return _refuse_probe(name)
                raise ImportError(_msg(name))
            if (top in _STDLIB or top in _ALLOWED_THIRD_PARTY
                    or top in ("__main__", "sitecustomize", "usercustomize")):
                return None
            # An installed package that is neither stdlib, allowed, nor blocked.
            # Decide by the frame that REALLY asked -- seen past importlib /
            # pkgutil / runpy -- not by the first stdlib file on the stack.
            if not _requester_is_sandbox(2):
                return None  # a genuine library's own import / probe
            if "." in name:
                return None  # submodule of a package already allowed
            import importlib.machinery
            spec = importlib.machinery.PathFinder.find_spec(name, path)
            if spec is not None:
                if spec.origin and _in_sandbox(spec.origin):
                    return None
                locs = spec.submodule_search_locations or []
                if locs and all(_in_sandbox(p) for p in locs):
                    return None
            if _is_probe(sys._getframe(1)) and _probe_caller_is_direct_sandbox():
                return _refuse_probe(name)  # graceful None for a direct probe
            raise ImportError(_msg(name))

    sys.meta_path.insert(0, _KeshevImportWall())

    # ---- file jail (audit hook) --------------------------------------------
    # READ allow-list: the sandbox plus the python install / site-packages
    # (so numpy/torch/scipy load) and a minimal set of system paths. WRITE is
    # sandbox-only (plus the null/std sinks). ~/.ssh, other homes, /proc/<pid>
    # of live jobs and the sealed eval tree ~/keshev7-eval are outside both.
    _READ_ROOTS = set()
    for _p in ("/usr", "/lib", "/lib64", "/lib32", "/bin", "/sbin", "/etc",
               "/opt", "/proc/self", "/proc/cpuinfo", "/proc/meminfo",
               "/proc/loadavg", "/proc/stat", "/proc/uptime", "/proc/version",
               "/sys/devices/system/cpu", "/dev/null", "/dev/zero",
               "/dev/full", "/dev/urandom", "/dev/random", "/dev/tty",
               "/dev/stdin", "/dev/stdout", "/dev/stderr", "/dev/fd",
               "/dev/shm", "/dev/ptmx", "/run/user"):
        _READ_ROOTS.add(_p)
    try:
        for _p in (sys.prefix, sys.base_prefix, sys.exec_prefix,
                   sys.base_exec_prefix):
            if _p:
                _READ_ROOTS.add(os.path.realpath(_p))
    except Exception:
        pass
    for _p in list(sys.path):
        try:
            if _p and os.path.isdir(_p):
                _READ_ROOTS.add(os.path.realpath(_p))
        except Exception:
            pass
    try:
        import site as _site
        _cands = list(getattr(_site, "getsitepackages", lambda: [])())
        try:
            _cands.append(_site.getusersitepackages())
        except Exception:
            pass
        for _p in _cands:
            if _p:
                _READ_ROOTS.add(os.path.realpath(_p))
    except Exception:
        pass
    try:
        import sysconfig as _sc
        for _k in ("stdlib", "platstdlib", "purelib", "platlib", "data"):
            try:
                _v = _sc.get_path(_k)
                if _v:
                    _READ_ROOTS.add(os.path.realpath(_v))
            except Exception:
                pass
    except Exception:
        pass

    _WRITE_ROOTS = ("/dev/null", "/dev/zero", "/dev/full", "/dev/stdout",
                    "/dev/stderr", "/dev/tty", "/dev/shm", "/dev/ptmx")

    _O_WRITE = 0
    for _n in ("O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_APPEND"):
        _O_WRITE |= getattr(os, _n, 0)

    import threading as _threading
    _busy = _threading.local()

    def _resolve(path):
        try:
            path = os.fspath(path)
        except TypeError:
            return None
        if isinstance(path, bytes):
            try:
                path = path.decode("utf-8", "surrogateescape")
            except Exception:
                return None
        if not isinstance(path, str) or not path:
            return None
        try:
            if not os.path.isabs(path):
                path = os.path.join(os.getcwd(), path)
            # normalise .. and the leaf symlink target without following the
            # whole chain (dirname realpath handles symlinked parents)
            d = os.path.dirname(path)
            rd = os.path.realpath(d) if d else os.getcwd()
            return os.path.normpath(os.path.join(rd, os.path.basename(path)))
        except Exception:
            return None

    def _within(rp, roots):
        for r in roots:
            if rp == r or rp.startswith(r.rstrip("/") + "/"):
                return True
        return False

    def _read_ok(rp):
        return rp.startswith(_PREFIX) or rp == _SANDBOX or _within(rp, _READ_ROOTS)

    def _write_ok(rp):
        return rp.startswith(_PREFIX) or rp == _SANDBOX or _within(rp, _WRITE_ROOTS)

    # READ-ONLY SOURCE DATA inside the sandbox (Iddo's labeled clips and his
    # unlabeled Cafe audio): no write/chmod/rename/link/delete into it - checked
    # on the REAL target (symlinks), on fd and dir_fd forms - and no
    # rename/rmdir/rmtree/chmod of a folder that contains it (e.g. `data`).
    _RO_DIRS = tuple(os.path.realpath(os.path.join(_SANDBOX, "data", _d))
                     for _d in ("train", "unlabeled"))

    def _fd_target(fd):
        if isinstance(fd, bool) or not isinstance(fd, int) or fd < 0:
            return None
        try:
            t = os.readlink("/proc/self/fd/%d" % fd)
        except Exception:
            return None
        return t if t.startswith("/") else None

    def _ro_real(path, dir_fd=None, follow=True):
        try:
            if isinstance(path, int) and not isinstance(path, bool):
                t = _fd_target(path)
                return os.path.normpath(t) if t else None
            path = os.fspath(path)
            if isinstance(path, bytes):
                path = path.decode("utf-8", "surrogateescape")
            if not isinstance(path, str) or not path:
                return None
            if not os.path.isabs(path):
                path = os.path.join(_fd_target(dir_fd) or os.getcwd(), path)
            if follow:
                return os.path.realpath(path)
            d = os.path.dirname(path)
            return os.path.normpath(os.path.join(os.path.realpath(d) if d else os.getcwd(),
                                                 os.path.basename(path)))
        except Exception:
            return None

    def _ro_hit(rp, ancestor=False):
        if not rp:
            return False
        for d in _RO_DIRS:
            if rp == d or rp.startswith(d + "/"):
                return True
            if ancestor and (rp == _SANDBOX or rp.startswith(_PREFIX)) and d.startswith(rp.rstrip("/") + "/"):
                return True
        return False

    def _deny_ro(kind, rp):
        raise PermissionError(
            "KESHEV7 GUARD: %s refused: %s is (or contains) read-only source data "
            "(data/train, data/unlabeled) - write features/checkpoints in your own "
            "folders" % (kind, rp))

    # event -> (index of dir_fd in the audit args or None, follows the leaf symlink, ancestor rule)
    _RO_EVENTS = {
        "os.remove": (1, False, False), "os.rmdir": (1, False, True),
        "shutil.rmtree": (1, False, True), "os.chmod": (2, True, True),
        "os.chown": (3, True, True), "os.mkdir": (2, False, False),
        "os.utime": (3, True, False), "os.truncate": (None, True, False),
        "os.setxattr": (None, True, False), "os.removexattr": (None, True, False),
    }

    def _deny(kind, rp):
        raise PermissionError(
            "KESHEV7 GUARD: %s outside the sandbox refused: %s "
            "(your python may read the sandbox + libraries and write only the "
            "sandbox)" % (kind, rp))

    _WRITE_ONLY_EVENTS = frozenset((
        "os.remove", "os.unlink", "os.rmdir", "os.truncate", "os.chmod",
        "os.chown", "os.mkdir", "os.makedirs", "os.utime",
        "os.removexattr", "os.setxattr", "shutil.rmtree"))
    _TWO_PATH_EVENTS = frozenset(("os.rename", "os.replace", "os.link", "os.symlink"))

    def _hook(event, args):
        if getattr(_busy, "on", False):
            return
        try:
            _busy.on = True
            if event == "open":
                path = args[0] if args else None
                mode = args[1] if len(args) > 1 else None
                flags = args[2] if len(args) > 2 else None
                rp = _resolve(path)
                if rp is None:
                    return
                is_write = False
                if isinstance(mode, str):
                    is_write = any(ch in mode for ch in "wax+")
                elif isinstance(flags, int):
                    is_write = bool(flags & _O_WRITE)
                if is_write:
                    if not _write_ok(rp):
                        _deny("write", rp)
                    rr = _ro_real(path)
                    if _ro_hit(rr):
                        _deny_ro("write", rr)
                else:
                    if not _read_ok(rp):
                        _deny("read", rp)
            elif event in _TWO_PATH_EVENTS:
                for a in args[:2]:
                    rp = _resolve(a)
                    if rp is not None and not _write_ok(rp):
                        _deny("write", rp)
                fds = [a if isinstance(a, int) and not isinstance(a, bool) else None
                       for a in (list(args[2:4]) + [None, None])[:2]]
                if event == "os.symlink":      # (src, dst, dir_fd): only the new name matters
                    checks = [(_ro_real(args[1], fds[0], False), False)] if len(args) > 1 else []
                elif event == "os.link":       # a hard link shares the source inode
                    checks = [(_ro_real(args[0], fds[0], True), False),
                              (_ro_real(args[1], fds[1], False), False)] if len(args) > 1 else []
                else:                          # rename / replace
                    checks = [(_ro_real(args[0], fds[0], False), True),
                              (_ro_real(args[1], fds[1], False), True)] if len(args) > 1 else []
                for rr, anc in checks:
                    if _ro_hit(rr, ancestor=anc):
                        _deny_ro(event, rr)
            elif event in _WRITE_ONLY_EVENTS:
                rp = _resolve(args[0]) if args else None
                if rp is not None and not _write_ok(rp):
                    _deny("write", rp)
                spec = _RO_EVENTS.get(event)
                if spec and args:
                    i, follow, anc = spec
                    dfd = args[i] if i is not None and len(args) > i else None
                    rr = _ro_real(args[0], dfd, follow)
                    if _ro_hit(rr, ancestor=anc):
                        _deny_ro(event, rr)
        finally:
            _busy.on = False

    try:
        sys.addaudithook(_hook)
    except Exception:
        pass
