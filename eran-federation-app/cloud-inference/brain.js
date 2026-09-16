// brain.js — the read-only half of ERAN's brain: recognition, never learning.
//
// A port of eran-brain/body/brain.py:nearest() and nothing else. The cloud
// holds a SNAPSHOT of the prototypes and may look up which one a sound is
// closest to. It may not spawn one, pull one, scar one or forget one — every
// one of those is learning, learning happens on the fleet, and a second copy
// of ERAN learning in a Worker would be a second ERAN.
//
//   attraction = cosine(vec, proto) - proto.scar
//
// All prototype vectors are already L2-normalised, so the cosine is a plain
// dot product. A scarred prototype pulls less: that is the down-tap doing its
// work, carried over from the parent's hand on the fleet.

export const BRAIN_SCHEMA = "eran-brain-public-v1";

export class Brain {
  // snapshot: { schema, beat, dim, protos: [{ vec:[...], scar, mass, ... }] }
  constructor(snapshot) {
    if (!snapshot || !Array.isArray(snapshot.protos)) {
      throw new Error("brain snapshot has no protos array");
    }
    this.beat = snapshot.beat ?? null;
    this.dim = snapshot.dim ?? (snapshot.protos[0]?.vec?.length ?? 0);
    this.n = snapshot.protos.length;
    this.scars = new Float64Array(this.n);
    this.mass = new Float64Array(this.n);
    this.mat = new Float64Array(this.n * this.dim);
    for (let i = 0; i < this.n; i++) {
      const p = snapshot.protos[i];
      if (!p.vec || p.vec.length !== this.dim) {
        throw new Error(`prototype ${i} has dim ${p.vec ? p.vec.length : "none"}, expected ${this.dim}`);
      }
      this.mat.set(p.vec, i * this.dim);
      this.scars[i] = p.scar || 0;
      this.mass[i] = p.mass || 0;
    }
  }

  // (index, cosine sim, attraction) of the best prototype, plus the runners-up.
  nearest(vec, topK = 5) {
    if (vec.length !== this.dim) {
      throw new Error(`vector has dim ${vec.length}, brain wants ${this.dim}`);
    }
    const sims = new Float64Array(this.n);
    let best = -Infinity, bestI = -1;
    for (let i = 0; i < this.n; i++) {
      const off = i * this.dim;
      let s = 0;
      for (let d = 0; d < this.dim; d++) s += this.mat[off + d] * vec[d];
      sims[i] = s;
      const att = s - this.scars[i];
      if (att > best) { best = att; bestI = i; }
    }
    if (bestI < 0) return { index: null, sim: 0, att: 0, top: [] };
    const order = Array.from({ length: this.n }, (_, i) => i)
      .sort((a, b) => (sims[b] - this.scars[b]) - (sims[a] - this.scars[a]))
      .slice(0, topK);
    return {
      index: bestI,
      sim: sims[bestI],
      att: best,
      surprise: 1 - sims[bestI],
      top: order.map((i) => ({
        index: i, sim: sims[i], att: sims[i] - this.scars[i], mass: this.mass[i],
      })),
    };
  }
}
