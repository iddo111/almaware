# -*- coding: utf-8 -*-
"""Does rule_decisive do what its docstring claims? Hand cases, checked, before any GPU hour.

The claim under test is the one Iddo made: a court does not average the minority in.
The old rule() is a softmax over company - still an average. This must not be."""
import sys, torch

sys.path.insert(0, "/home/eran2/miko-bench/model")
sys.path.insert(0, r"D:\CLAUDE\miko\model")
from sefirot import ColumnTriad

t = ColumnTriad(4, 4)
cases = {
    "[0,9,10]  bloc=(9,10)": [0., 9., 10.],
    "[0,1,10]  bloc=(0,1)": [0., 1., 10.],
    "[5,5,5]   unanimous": [5., 5., 5.],
    "[1,2,3]   even spread": [1., 2., 3.],
    "[-4,0,0.5] bloc=(0,.5)": [-4., 0., 0.5],
}
hdr = ("case", "theta=0", "theta=1", "theta=inf", "median", "mean", "softbloc", "dissent")
print("%-24s%10s%10s%11s%9s%8s%10s%9s" % hdr)
for name, v in cases.items():
    s = torch.tensor(v).view(3, 1, 1).expand(3, 1, 4).contiguous()
    r0, d = t.rule_decisive(s, 0.0)
    r1, _ = t.rule_decisive(s, 1.0)
    ri, _ = t.rule_decisive(s, 1e9)
    med = s.median(0).values
    mean = s.mean(0)
    sb, _ = t.rule(s)
    print("%-24s%10.3f%10.3f%11.3f%9.3f%8.3f%10.3f%9.3f"
          % (name, r0[0, 0], r1[0, 0], ri[0, 0], med[0, 0], mean[0, 0], sb[0, 0], d[0, 0]))

print("\ngradient: does the DISCARDED seat receive gradient? (it must not - that is what")
print("'discarded' means, and it is the risk this rule carries)")
a = torch.tensor([[0.]], requires_grad=True)
b = torch.tensor([[1.]], requires_grad=True)
c = torch.tensor([[10.]], requires_grad=True)
r, _ = t.rule_decisive(torch.stack((a, b, c), 0), 0.0)
r.sum().backward()
print("   seats [0,1,10] theta=0 -> d(ruling)/d(seat) =",
      [float(x.grad) for x in (a, b, c)])
print("   expected [0.5, 0.5, 0.0]: the bloc rules in full, the outlier is out")

print("\nsanity: theta->inf must equal the plain mean exactly")
s = torch.randn(3, 8, 5)
ri, _ = t.rule_decisive(s, 1e9)
print("   max |decisive(theta=inf) - mean| =", float((ri - s.mean(0)).abs().max()))
r0, _ = t.rule_decisive(s, 0.0)
print("   max |decisive(theta=0)   - mean| =", float((r0 - s.mean(0)).abs().max()),
      " (must be > 0, or the rule is not deciding anything)")
print("   max |decisive(theta=0) - median| =", float((r0 - s.median(0).values).abs().max()),
      " (must be > 0, or it is just a median)")
