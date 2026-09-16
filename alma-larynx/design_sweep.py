# -*- coding: utf-8 -*-
"""design_sweep.py — search the PHYSICAL fold design space with the simulator as judge.

Iddo's order (2026-08-25 10:22): swarm the throat design using everything we
know — the two-mass simulator (ours), Sawada's rig numbers (Japanese: thin
two-layer cords + ONE TENSION MOTOR gave F0 110-350 Hz at ~2 kPa), the
child-larynx target band (ERAN's frozen ear needs F0 220-330 Hz — the frog
scar), and the fact that we own servos (tension is actuatable).

WHY REV-A FAILED (measured, simulate_voicebox.py): a SOLID Ecoflex block is
~15x too stiff and ~7x too heavy — silent at 2 kPa, and even at 5 kPa buzzes
at 75 Hz, far below the child band.

REV-B CONCEPT this sweep explores: the fold is a bending LIP (a shell cast
around a back-pocket core), not a block:
    k_bend = E * L * t^3 / (4 * l^3)     (cantilever of width L, thickness t,
    m      = rho * L * t * l              free height l)
    servo tension multiplies stiffness:  k_eff = k_bend * (1 + tau)
    (rubber under pre-strain stiffens ~linearly at small strain; Sawada's
    tension motor swept F0 3:1, so tau in [0, 3] is his demonstrated range.)

Design variables:
    L      fold length along airflow slot     8 - 17 mm
    t      lip wall thickness                 1 - 4 mm
    l      lip free height                    3 - 8 mm
    G0     rest half-gap                      0.2 - 0.8 mm
    E      Ecoflex modulus: 00-10 ~= 36 kPa, 00-30 ~= 69 kPa (literature)
    tau    servo pre-tension factor           0 (slack) - 3 (Sawada max)

ACCEPT (a design worth printing) =
    phonates at Ps <= 2000 Pa (the +200 hPa Sawada supply)  AND
    at SOME tau in range, F0 lands in [220, 330] Hz          AND
    modulation depth >= 0.2 (a real buzz, not a tremble)
The servo makes F0 a CONTROL, not a property: we accept if the band is
REACHABLE by tension, and report the tau that reaches it.

Honesty: same model limits as simulate_voicebox.py (two-mass, decoupled
filter, literature E). This picks the region to print — the pour proves it.
"""
import itertools
import json
import numpy as np

import simulate_voicebox as sv

RHO = 1070.0

def fold_params_shell(E, L, t, l, tau):
    k_total = E * L * t ** 3 / (4 * l ** 3) * (1 + tau)
    m_total = RHO * L * t * l
    m1, m2 = 0.8 * m_total, 0.2 * m_total
    k1, k2 = 0.75 * k_total, 0.25 * k_total
    kc = 0.3 * k_total
    return m1, m2, k1, k2, kc

def simulate(Ps, E, L, t, l, G0, tau, seconds=0.55):
    """Two-mass run with shell parameters; returns (osc, F0, depth)."""
    m1, m2, k1, k2, kc = fold_params_shell(E, L, t, l, tau)
    z1, z2 = 0.1, 0.6
    r1 = 2 * z1 * np.sqrt(m1 * k1); r2 = 2 * z2 * np.sqrt(m2 * k2)
    c1, c2 = 3 * k1, 3 * k2
    d1, d2 = 0.6 * l, 0.4 * l
    x1 = x2 = v1 = v2 = 0.0
    fs = 44100; n = int(seconds * fs); dt = 1.0 / fs
    U = np.zeros(n)
    for i in range(n):
        a1 = L * (G0 + x1); a2 = L * (G0 + x2)      # hemilarynx: one moving lip
        amin = min(a1, a2)
        if amin > 0 and a1 > 0:
            P1 = Ps * (1 - (amin / a1) ** 2) if a1 > amin else 0.5 * Ps
        else:
            P1 = Ps
        F1 = L * d1 * P1
        col1 = c1 * (-(G0 + x1)) if (G0 + x1) < 0 else 0.0
        col2 = c2 * (-(G0 + x2)) if (G0 + x2) < 0 else 0.0
        a1dd = (F1 - r1 * v1 - k1 * x1 - kc * (x1 - x2) + col1) / m1
        a2dd = (-r2 * v2 - k2 * x2 - kc * (x2 - x1) + col2) / m2
        v1 += a1dd * dt; x1 += v1 * dt
        v2 += a2dd * dt; x2 += v2 * dt
        U[i] = np.sqrt(2 * Ps / sv.RHO_AIR) * amin if amin > 0 else 0.0
    return sv.analyze(U)

def main():
    Ls  = [8e-3, 12e-3, 17e-3]
    ts  = [1e-3, 1.5e-3, 2e-3, 3e-3, 4e-3]
    ls  = [3e-3, 4e-3, 5e-3, 6e-3, 8e-3]
    G0s = [0.2e-3, 0.4e-3, 0.8e-3]
    Es  = [(36e3, "00-10"), (69e3, "00-30")]
    taus = [0.0, 1.0, 2.0, 3.0]

    winners = []
    tried = 0
    for (E, ename), L, t, l, G0 in itertools.product(Es, Ls, ts, ls, G0s):
        # quick physical sanity: lip must be thinner than its height to bend
        if t >= l:
            continue
        tried += 1
        # must phonate at 2 kPa with slack tension OR any tension
        band_hit = None; onset2k = False
        for tau in taus:
            osc, f0, depth = simulate(2000, E, L, t, l, G0, tau)
            if osc and depth >= 0.2:
                onset2k = True
                if 220 <= f0 <= 330:
                    band_hit = (tau, f0, depth)
                    break
        if onset2k and band_hit:
            winners.append({"E": ename, "L_mm": L * 1e3, "t_mm": t * 1e3,
                            "l_mm": l * 1e3, "G0_mm": G0 * 1e3,
                            "tau": band_hit[0], "F0": round(band_hit[1], 1),
                            "depth": round(band_hit[2], 2)})
            print(f"ACCEPT E={ename} L={L*1e3:.0f} t={t*1e3:.1f} l={l*1e3:.0f} "
                  f"G0={G0*1e3:.1f} tau={band_hit[0]} -> F0={band_hit[1]:.0f}Hz "
                  f"depth={band_hit[2]:.2f}")
    print(f"\nswept {tried} geometries x 4 tensions; {len(winners)} accepted")
    json.dump(winners, open(r"D:\CLAUDE\alma-larynx\DESIGN-SWEEP-winners.json", "w"),
              indent=1)
    print("saved DESIGN-SWEEP-winners.json")

if __name__ == "__main__":
    main()
