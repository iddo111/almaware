"""scarlint -- the house's own scars, as an executable check.

The argument this file makes: a lesson that can be a static check should be a static
check, not a paragraph. A document has to be remembered or retrieved; a check just fires.
This implements the four code-level scars from lessons.jsonl that are mechanically
detectable, and it is proven against the real files that carried them.

  set PYTHONIOENCODING=utf-8 && python scarlint.py <path> [<path> ...]

Exit code 1 if any finding. Pure stdlib AST -- nothing to install, no model, no network.
"""
from __future__ import annotations

import ast
import os
import sys

# lesson id -> (short name, why it matters)
SCARS = {
    "mem-018": ("layernorm-size-1",
                "nn.LayerNorm over a size-1 axis is identically zero: the head is a constant function"),
    "core-015": ("inverted-contrastive-temperature",
                 "CLIP stores log(1/t); storing log(t) makes exp() the reciprocal, ~204x too small"),
    "core-016": ("frozen-best-checkpoint",
                 "strict > against a metric pinned at its floor never overwrites after the first epoch"),
    "core-020": ("rmtree-on-root",
                 "recursive delete of a directory root lets a tool erase itself; clear contents instead"),
}


class Finding:
    def __init__(self, path, line, lesson, detail):
        self.path, self.line, self.lesson, self.detail = path, line, lesson, detail

    def __str__(self):
        name, why = SCARS[self.lesson]
        return (f"{self.path}:{self.line}: [{self.lesson} {name}] {self.detail}\n"
                f"    why: {why}")


def _is_layernorm(node):
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr == "LayerNorm") or \
           (isinstance(f, ast.Name) and f.id == "LayerNorm")


def _const_num(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    # torch.tensor(0.07) / float(0.07)
    if isinstance(node, ast.Call) and node.args:
        f = node.func
        nm = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
        if nm in ("tensor", "float", "Tensor", "as_tensor"):
            return _const_num(node.args[0])
    return None


# A scar encoded as a regression test LOOKS exactly like the scar. Skip those, or the
# check fires on the very test written to prove the check is needed. (Found the hard way:
# the first run flagged miko/model/bench.py:111, which is `layernorm_scar()` -- a test
# that deliberately constructs LayerNorm(1) to prove it is dead.)
EXEMPT_FILES = ("bench.py", "scar_guard.py", "conftest.py", "scarlint.py")
EXEMPT_NAME_PARTS = ("test", "scar", "guard", "regress", "demo", "example")


def _exempt_file(path):
    b = os.path.basename(path)
    return b in EXEMPT_FILES or b.startswith("test_") or b.endswith("_test.py")


class Visitor(ast.NodeVisitor):
    def __init__(self, path, src):
        self.path, self.src = path, src
        self.out: list[Finding] = []
        self._fn_stack: list[str] = []

    def _in_exempt_fn(self):
        return any(any(p in n.lower() for p in EXEMPT_NAME_PARTS) for n in self._fn_stack)

    def visit_FunctionDef(self, node):
        self._fn_stack.append(node.name)
        self.generic_visit(node)
        self._fn_stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _add(self, node, lesson, detail):
        if self._in_exempt_fn():
            return
        self.out.append(Finding(self.path, node.lineno, lesson, detail))

    # --- mem-018: LayerNorm(1) --------------------------------------------
    def visit_Call(self, node):
        if _is_layernorm(node) and node.args:
            v = _const_num(node.args[0])
            if v == 1:
                self.out.append(Finding(self.path, node.lineno, "mem-018",
                                        "LayerNorm(1) normalises over one element"))
            if isinstance(node.args[0], (ast.List, ast.Tuple)) and len(node.args[0].elts) == 1:
                if _const_num(node.args[0].elts[0]) == 1:
                    self.out.append(Finding(self.path, node.lineno, "mem-018",
                                            "LayerNorm([1]) normalises over one element"))

        # --- core-020: rmtree on something that looks like a root ----------
        f = node.func
        nm = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")
        if nm == "rmtree" and node.args:
            a = node.args[0]
            txt = ast.unparse(a) if hasattr(ast, "unparse") else ""
            bare_root = isinstance(a, ast.Name) or (
                isinstance(a, ast.Attribute) and a.attr in ("root", "dir", "path", "parent", "cwd"))
            if bare_root and "/" not in txt and "join" not in txt:
                self.out.append(Finding(self.path, node.lineno, "core-020",
                                        f"rmtree({txt}) targets a directory root, not its contents"))
        self.generic_visit(node)

    # --- core-015: log-temperature with the sign backwards ----------------
    def visit_Assign(self, node):
        tgt = ast.unparse(node.targets[0]) if hasattr(ast, "unparse") else ""
        val = node.value
        # unwrap nn.Parameter(...)
        inner = val
        if isinstance(inner, ast.Call):
            fn = inner.func
            nm = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
            if nm == "Parameter" and inner.args:
                inner = inner.args[0]
        # looking for  <something>.log()  where something is a constant < 1
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) \
                and inner.func.attr == "log":
            base = _const_num(inner.func.value)
            if base is not None and 0 < base < 1 and ("temp" in tgt.lower() or "scale" in tgt.lower()):
                self.out.append(Finding(
                    self.path, node.lineno, "core-015",
                    f"{tgt} = log({base:g}); exp() gives {base:g}, not {1/base:.4g} "
                    f"-- CLIP stores log(1/t)"))
        self.generic_visit(node)

    # --- core-016: best-metric guard with no did-it-move assertion --------
    def visit_If(self, node):
        t = node.test
        if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Gt):
            right = ast.unparse(t.comparators[0]) if hasattr(ast, "unparse") else ""
            if "best" in right.lower():
                body = ast.unparse(node) if hasattr(ast, "unparse") else ""
                if "save" in body.lower() or "torch.save" in body:
                    self.out.append(Finding(
                        self.path, node.lineno, "core-016",
                        f"strict > against {right}: if the metric never leaves its floor, "
                        f"only the first epoch is ever saved"))
        self.generic_visit(node)


def scan(path):
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
        tree = ast.parse(src, filename=path)
    except (SyntaxError, OSError) as e:
        print(f"{path}: skipped ({e.__class__.__name__})", file=sys.stderr)
        return []
    v = Visitor(path, src)
    v.visit(tree)
    return v.out


def main(argv):
    targets = argv[1:] or ["."]
    files = []
    for t in targets:
        if os.path.isfile(t):
            files.append(t)
        else:
            for dp, dns, fns in os.walk(t):
                dns[:] = [d for d in dns if d not in
                          {".git", "node_modules", "__pycache__", ".venv", "venv", "site-packages"}]
                files += [os.path.join(dp, f) for f in fns if f.endswith(".py")]
    findings = []
    for f in files:
        findings += scan(f)
    for f in findings:
        print(f)
    print(f"\nscarlint: {len(files)} file(s), {len(findings)} finding(s) "
          f"across {len(SCARS)} encoded scars")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
