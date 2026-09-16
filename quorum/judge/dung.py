# לזכרה של עלמה ז״ל
"""QUORUM · judge · dung — WHO SURVIVES THE ARGUMENT, computed, not judged.

An abstract argumentation framework: nodes (claims and קושיות) and a single
relation, "x attacks y". A תירוץ is not a special kind of object — it is an
attack ON the קושיא. That is exactly right for the Talmudic form and it is why
this formalism was chosen: קושיא attacks the דעה, תירוץ attacks the קושיא, and
whether the דעה stands falls out of the graph instead of out of anyone's taste.

GROUNDED SEMANTICS (Dung 1995), the most sceptical of the standard semantics —
it grants nothing it is not forced to grant:

    IN        every attacker of x is OUT       -> x survives
    OUT       some attacker of x is IN         -> x is defeated
    UNDECIDED neither                          -> the argument is a standoff

The least fixed point is reached by repeatedly marking the unattacked IN and
whatever they defeat OUT, until nothing changes. Mutual attacks with no outside
support settle to UNDECIDED — and UNDECIDED is not a failure of the judge, it is
the correct report of an unresolved מחלוקת. It is one of the two roads to
CANNOT RULE.

Deterministic, terminating, ~50 lines, 100% ours. No model is consulted.
"""
from __future__ import annotations

IN, OUT, UNDECIDED = "in", "out", "undecided"


def grounded(nodes: list, attacks: list) -> dict:
    """nodes: [id]; attacks: [(attacker_id, target_id)] -> {id: IN|OUT|UNDECIDED}.

    Attacks whose attacker or target is unknown are ignored rather than raising:
    a malformed edge must not be able to silently flip a verdict, and it must not
    crash a ruling either."""
    ids = list(dict.fromkeys(nodes))
    known = set(ids)
    edges = [(a, t) for a, t in attacks if a in known and t in known]
    attackers = {i: set() for i in ids}
    for a, t in edges:
        attackers[t].add(a)

    label = {i: UNDECIDED for i in ids}
    changed = True
    while changed:
        changed = False
        for i in ids:
            if label[i] != UNDECIDED:
                continue
            atk = attackers[i]
            if all(label[a] == OUT for a in atk):        # vacuously true if unattacked
                label[i] = IN
                changed = True
            elif any(label[a] == IN for a in atk):
                label[i] = OUT
                changed = True
    return label


def surviving_attacks(claim_id: str, attacks: list, label: dict) -> list:
    """The קושיות aimed at this claim that were NOT put down (IN or UNDECIDED).
    An UNDECIDED attack still counts as unanswered — the sceptical reading. The
    judge must not treat a standoff as a defence."""
    return [a for a in attacks
            if a.attacks == claim_id and label.get(a.id, UNDECIDED) in (IN, UNDECIDED)]


def build(case) -> tuple:
    """Case -> (labels, edges). Nodes are every claim id and every attack id."""
    nodes = [c.id for c in case.claims] + [a.id for a in case.attacks]
    edges = [(a.id, a.attacks) for a in case.attacks if a.attacks]
    return grounded(nodes, edges), edges
