# לזכרה של עלמה ז״ל
"""QUORUM · judge · entail — THE SOLVER IS THE RULER, NOT A MEMBER.

Iddo asked for logic built into code. This is it. When a speaker says
"therefore", Z3 answers yes or no about the entailment AS STATED, and it does
not agree politely. Where the step fails it hands back a COUNTERMODEL: a
concrete world in which every stated premise holds and the conclusion does not.
That countermodel is the ruling's evidence, printable in the verdict.

Two questions are asked of the solver, and they are different questions:

  VALIDITY    Is  P1 & ... & Pn & not C  unsatisfiable?  (does C follow?)
  COHERENCE   Is  P1 & ... & Pn & C & K  satisfiable?    (can the claim coexist
              with the kushia that survived the argument graph?)

Keeping them apart is what stops the judge conflating "your reasoning is
invalid" with "your premise is false". Kropotkin's group-benefit step is
perfectly VALID modus ponens; what kills it is that the surviving kushia
(Williams 1966) is formally incompatible with his premise. Two different
findings, two different sentences in the verdict.

DO NOT FAKE FORMALISATION. A claim with no `formal` block gets ABSTAIN on these
gates and the verdict says so in words. Half the claims in any real argument are
not formalisable and pretending otherwise would be the exact failure the judge
exists to avoid.

THE MINI-LANGUAGE, parsed with Python's own `ast` under a strict whitelist --
never eval, never exec:

    bare name            -> Bool          widespread
    and / or / not       -> boolean ops   widespread and not needs_explanation
    implies(a, b)        -> a => b        implies(species_benefit, kept)
    iff(a, b)            -> a <=> b
    name(x)              -> predicate over the one universe sort U
    forall x: expr       -> universal     forall p: holds(p)
    exists x: expr       -> existential   exists p: dense(p) and not holds(p)
    numeric comparison   -> Real          benefit > cost

A name is a Bool until it appears in a comparison, when it becomes a Real; a
name that is called is a predicate U->Bool. Nothing else is accepted.
"""
from __future__ import annotations

import ast
import re

try:
    import z3
    Z3_OK = True
    Z3_VERSION = z3.get_version_string()
except Exception:                                    # failure-is-a-value
    z3 = None
    Z3_OK = False
    Z3_VERSION = ""

_QUANT = re.compile(r"^\s*(forall|exists)\s+([A-Za-z_]\w*)\s*:\s*(.+)$", re.S)


class FormalError(ValueError):
    """The expression is outside the mini-language. Never swallowed: a formula
    the judge cannot read must not quietly become a formula it ruled on."""


class _Env:
    """One shared namespace per formula group, so `kept` means the same thing in
    a premise and in the conclusion."""

    def __init__(self):
        self.U = z3.DeclareSort("U")
        self.bools, self.reals, self.preds, self.vars = {}, {}, {}, {}

    def boolean(self, n):
        if n in self.reals:
            raise FormalError(n + " used both as a proposition and as a quantity")
        return self.bools.setdefault(n, z3.Bool(n))

    def real(self, n):
        if n in self.bools:
            raise FormalError(n + " used both as a proposition and as a quantity")
        return self.reals.setdefault(n, z3.Real(n))

    def pred(self, n):
        return self.preds.setdefault(n, z3.Function(n, self.U, z3.BoolSort()))


def _walk(node, env):
    if isinstance(node, ast.Expression):
        return _walk(node.body, env)
    if isinstance(node, ast.BoolOp):
        vals = [_walk(v, env) for v in node.values]
        return z3.And(*vals) if isinstance(node.op, ast.And) else z3.Or(*vals)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return z3.Not(_walk(node.operand, env))
    if isinstance(node, ast.Name):
        return env.vars[node.id] if node.id in env.vars else env.boolean(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, bool):
        return z3.BoolVal(node.value)
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormalError("only plain named calls are allowed")
        fn = node.func.id
        args = [_walk(a, env) for a in node.args]
        if fn == "implies":
            if len(args) != 2:
                raise FormalError("implies() takes exactly 2 arguments")
            return z3.Implies(args[0], args[1])
        if fn == "iff":
            if len(args) != 2:
                raise FormalError("iff() takes exactly 2 arguments")
            return args[0] == args[1]
        if len(args) != 1:
            raise FormalError("predicate " + fn + " takes exactly 1 argument")
        return env.pred(fn)(args[0])
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1:
            raise FormalError("chained comparisons are not allowed")
        left = _num(node.left, env)
        right = _num(node.comparators[0], env)
        op = node.ops[0]
        for t, f in ((ast.Gt, lambda a, b: a > b), (ast.GtE, lambda a, b: a >= b),
                     (ast.Lt, lambda a, b: a < b), (ast.LtE, lambda a, b: a <= b),
                     (ast.Eq, lambda a, b: a == b), (ast.NotEq, lambda a, b: a != b)):
            if isinstance(op, t):
                return f(left, right)
    raise FormalError("unsupported syntax: " + type(node).__name__)


def _num(node, env):
    if isinstance(node, ast.Name):
        return env.vars[node.id] if node.id in env.vars else env.real(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return z3.RealVal(node.value)
    if isinstance(node, ast.BinOp):
        lhs, rhs = _num(node.left, env), _num(node.right, env)
        for t, f in ((ast.Add, lambda a, b: a + b), (ast.Sub, lambda a, b: a - b),
                     (ast.Mult, lambda a, b: a * b), (ast.Div, lambda a, b: a / b)):
            if isinstance(node.op, t):
                return f(lhs, rhs)
    raise FormalError("only names, numbers and + - * / are allowed in a quantity")


def parse(expr, env):
    """One expression -> one Z3 term. Raises FormalError on anything unreadable."""
    expr = (expr or "").strip()
    if not expr:
        raise FormalError("empty expression")
    m = _QUANT.match(expr)
    if m:
        kind, var, body = m.group(1), m.group(2), m.group(3)
        c = z3.Const(var, env.U)
        prev = env.vars.get(var)
        env.vars[var] = c
        try:
            inner = parse(body, env)
        finally:
            if prev is None:
                env.vars.pop(var, None)
            else:
                env.vars[var] = prev
        return z3.ForAll([c], inner) if kind == "forall" else z3.Exists([c], inner)
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise FormalError("cannot parse: " + str(e.msg))
    return _walk(tree, env)


def _model_text(model):
    """The countermodel, in the arguer's own vocabulary. This is what makes an
    invalid step arguable-with rather than merely asserted."""
    bits = []
    for d in sorted(model.decls(), key=lambda d: d.name()):
        if d.arity():
            bits.append(d.name() + "(.)")
            continue
        try:
            s = str(model[d])
        except Exception:
            continue
        if s == "True":
            bits.append(d.name())
        elif s == "False":
            bits.append("not " + d.name())
        else:
            bits.append(d.name() + "=" + s)
    return ", ".join(bits) if bits else "(any world at all)"


def check(premises, conclusion, extra=None):
    """VALIDITY: do the STATED premises entail the conclusion?

    -> {"status": valid|invalid|unsound|abstain|error, "countermodel", "note"}
    `unsound` means the premises contradict each other, which entails anything --
    reported separately, because "it follows" is a worthless yes in that case.
    """
    if not Z3_OK:
        return {"status": "abstain", "countermodel": "",
                "note": "z3 not available on this machine"}
    if not conclusion or not premises:
        return {"status": "abstain", "countermodel": "",
                "note": "no premises or no conclusion were stated"}
    try:
        env = _Env()
        terms = [parse(p, env) for p in premises]
        terms += [parse(x, env) for x in (extra or [])]
        goal = parse(conclusion, env)
    except FormalError as e:
        return {"status": "error", "countermodel": "", "note": str(e)}

    s = z3.Solver()
    s.add(*terms)
    if s.check() == z3.unsat:
        return {"status": "unsound", "countermodel": "",
                "note": "the stated premises contradict each other"}
    s2 = z3.Solver()
    s2.add(*terms)
    s2.add(z3.Not(goal))
    r = s2.check()
    if r == z3.unsat:
        return {"status": "valid", "countermodel": "",
                "note": "the conclusion follows from the premises as stated"}
    if r == z3.sat:
        return {"status": "invalid", "countermodel": _model_text(s2.model()),
                "note": "a world exists where every stated premise holds "
                        "and the conclusion still fails"}
    return {"status": "abstain", "countermodel": "",
            "note": "z3 returned unknown -- no ruling on this gate"}


def coherent(premises, conclusion, attack_formulas):
    """COHERENCE: can the claim be held together with the kushia that survived?

    -> {"status": coherent|incompatible|abstain|error, "witness", "note"}
    `incompatible` is the strongest thing this judge ever says: the claim and the
    surviving objection cannot both be held, as formalised.
    """
    if not Z3_OK:
        return {"status": "abstain", "note": "z3 not available", "witness": ""}
    live = [a for a in (attack_formulas or []) if (a or "").strip()]
    if not live:
        return {"status": "abstain", "witness": "",
                "note": "no surviving kushia was formalised"}
    try:
        env = _Env()
        terms = [parse(p, env) for p in (premises or [])]
        if conclusion:
            terms.append(parse(conclusion, env))
        terms += [parse(a, env) for a in live]
    except FormalError as e:
        return {"status": "error", "note": str(e), "witness": ""}
    s = z3.Solver()
    s.add(*terms)
    r = s.check()
    if r == z3.unsat:
        return {"status": "incompatible", "witness": "",
                "note": "the claim cannot be held together with "
                        "the kushia that survived"}
    if r == z3.sat:
        return {"status": "coherent", "witness": _model_text(s.model()),
                "note": "claim and surviving kushia can both be held"}
    return {"status": "abstain", "witness": "", "note": "z3 returned unknown"}
