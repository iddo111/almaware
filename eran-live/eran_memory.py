"""eran_memory.py — Eran's long-term memory layer (v1).

Gives Eran PERSISTENT long-term memory + AUTOMATIC semantic retrieval (RAG-style):
Eran writes experiences/facts here, and auto-retrieves the most relevant ones to
inject into its context when it thinks. This is the BUILDABLE memory layer
(retrieval). The next stage — "memory emergent from the weights" (periodic
consolidation of these memories INTO the model via LoRA) — plugs in on top (see
consolidate() stub + the Grok handoff).

Self-contained: uses sentence-transformers (multilingual, good Hebrew) if present,
else a dependency-free offline char-ngram fallback so it always works.

לזכרה של עלמה ז"ל · ALMAWARE / iddoperez.ai
"""
import os, json, time, math, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "eran_longterm_memory.jsonl")


class _Embedder:
    """Multilingual embeddings (Hebrew-capable) with an offline fallback."""
    def __init__(self):
        self.model = None
        self.dim = 384
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            self.dim = self.model.get_sentence_embedding_dimension()
        except Exception:
            self.model = None  # fall back to hashed char 3-grams (offline, no deps)

    def embed(self, text):
        if self.model is not None:
            return list(map(float, self.model.encode(text, normalize_embeddings=True)))
        v = [0.0] * self.dim
        t = (text or "").strip()
        for i in range(max(1, len(t) - 2)):
            h = int(hashlib.md5(t[i:i + 3].encode("utf-8")).hexdigest(), 16) % self.dim
            v[h] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


_emb = None
def _embedder():
    global _emb
    if _emb is None:
        _emb = _Embedder()
    return _emb


def _cos(a, b):
    return sum(x * y for x, y in zip(a, b))  # vectors are L2-normalized


class LongTermMemory:
    def __init__(self, path=STORE):
        self.path = path
        self.items = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.items.append(json.loads(line))

    def add(self, text, meta=None, kind="episodic"):
        """Store a memory. kind: 'episodic' (events) / 'semantic' (facts) / 'person'."""
        rec = {"id": len(self.items) + 1, "text": text, "ts": time.time(),
               "kind": kind, "meta": meta or {}, "emb": _embedder().embed(text)}
        self.items.append(rec)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec["id"]

    def retrieve(self, query, k=5, min_score=0.15, kind=None):
        """Automatic semantic retrieval: top-k most relevant memories."""
        pool = [it for it in self.items if (kind is None or it.get("kind") == kind)]
        if not pool:
            return []
        q = _embedder().embed(query)
        scored = sorted(((_cos(q, it["emb"]), it) for it in pool), key=lambda x: -x[0])
        return [{"score": round(s, 3), "text": it["text"], "kind": it.get("kind"),
                 "meta": it["meta"]} for s, it in scored[:k] if s >= min_score]

    def auto_context(self, query, k=5, max_chars=1200):
        """Auto-pull relevant memories as a context block to feed Eran when it thinks."""
        out, total = [], 0
        for h in self.retrieve(query, k=k):
            line = f"- {h['text']}"
            if total + len(line) > max_chars:
                break
            out.append(line); total += len(line)
        return "\n".join(out)

    def consolidate(self):
        """STAGE 2 (stub) — 'memory emergent from weights': periodically fold these
        memories INTO Eran's model (LoRA/fine-tune) so they become intrinsic, not just
        retrieved. The hard, research-level step. See Grok handoff. Not yet implemented."""
        raise NotImplementedError("weight-consolidation is the next stage (Grok slice)")


if __name__ == "__main__":
    import sys
    m = LongTermMemory()
    if len(sys.argv) >= 3 and sys.argv[1] == "add":
        print("stored id", m.add(" ".join(sys.argv[2:])))
    elif len(sys.argv) >= 3 and sys.argv[1] == "ask":
        for h in m.retrieve(" ".join(sys.argv[2:])):
            print(f"[{h['score']}] {h['text']}")
    else:
        print(f"eran memory: {len(m.items)} items. usage: eran_memory.py add <text> | ask <query>")
        print("embedder:", "sentence-transformers" if _embedder().model else "offline char-ngram fallback")
