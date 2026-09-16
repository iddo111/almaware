"""Sequence-level knowledge probes for acoustic codebooks (pure numpy).

The question these answer is not "how small is the distortion" -- a prior
controlled experiment established that k-means distortion is not evidence of a
better speech representation. The question here is:

    when the same syllable is spoken again, does the ant emit the same unit
    string, and does a different syllable get a different one?

Everything is computed from the unit sequence an ant produces for audio it never
trained on. Syllable identity is a scoring key only: it is read from the corpus
label side-car, it never enters a feature, a codebook, or a checkpoint.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np

from acoustic_units import encode, features, load_wav


# --- speech span -----------------------------------------------------------
# Every synthetic file carries 10-80 ms of room tone padding at each end plus
# whatever silence the vocoder rendered. Left in, the unit string would be
# mostly "room tone" units and edit distance would be dominated by pad length.
# The floor is estimated per file from its own quietest frames.
NOISE_QUANTILE = 0.30
SPEECH_MARGIN_NATS = 1.5  # ~6.5 dB of power above the estimated floor
PAD = -1  # bank padding symbol; never equals a unit id


def speech_span(x: np.ndarray) -> tuple[int, int]:
    """First and last frame of the speech region (column 0 is log energy)."""
    e = x[:, 0]
    k = max(1, int(round(NOISE_QUANTILE * len(e))))
    floor = float(np.median(np.sort(e)[:k]))
    hit = np.flatnonzero(e >= floor + SPEECH_MARGIN_NATS)
    if hit.size < 3:  # no detectable burst; fall back to the whole file
        return 0, len(e)
    return int(hit[0]), int(hit[-1] + 1)


def collapse(ids: np.ndarray) -> np.ndarray:
    """Run-length collapse: the unit string, invariant to how long each unit held."""
    if len(ids) == 0:
        return ids
    keep = np.ones(len(ids), dtype=bool)
    keep[1:] = ids[1:] != ids[:-1]
    return ids[keep]


# --- batched edit distance -------------------------------------------------
# dp[i][j] = min(dp[i-1][j-1] + cost, dp[i-1][j] + 1, dp[i][j-1] + 1).
# The third term depends on the same row, so it is applied afterwards as
#   dp[i][j] = min_{j' <= j} (base[j'] + (j - j')) = j + cummin(base - j),
# which makes one whole DP row a handful of numpy operations over the entire
# bank at once. Exactness is checked against a reference implementation in
# tests/test_sequence_probes.py.

def pack(sequences: list[np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    lengths = np.asarray([len(s) for s in sequences], dtype=np.int64)
    width = int(lengths.max()) if len(lengths) else 0
    bank = np.full((len(sequences), width), PAD, dtype=np.int64)
    for row, s in enumerate(sequences):
        bank[row, :len(s)] = s
    return bank, lengths


def _dp(query: np.ndarray, bank: np.ndarray, first_row: np.ndarray) -> np.ndarray:
    n, width = bank.shape
    j = np.arange(width + 1, dtype=np.int32)
    prev = np.repeat(first_row[None, :], n, axis=0)
    base = np.empty((n, width + 1), dtype=np.int32)
    for i in range(1, len(query) + 1):
        cost = (bank != query[i - 1]).astype(np.int32)
        base[:, 0] = i
        np.minimum(prev[:, :-1] + cost, prev[:, 1:] + 1, out=base[:, 1:])
        prev = np.minimum.accumulate(base - j, axis=1) + j
    return prev


def edit_to_bank(query: np.ndarray, bank: np.ndarray, lengths: np.ndarray) -> np.ndarray:
    """Levenshtein distance from one sequence to every sequence in the bank."""
    width = bank.shape[1]
    prev = _dp(query, bank, np.arange(width + 1, dtype=np.int32))
    return prev[np.arange(len(bank)), lengths].astype(np.int64)


def substring_edit_to_bank(
    query: np.ndarray, bank: np.ndarray, lengths: np.ndarray
) -> np.ndarray:
    """Best match of `query` against any contiguous window of each bank sequence.

    Free start and free end in the bank sequence, so this asks "does this
    syllable's unit string appear anywhere inside this word's unit string".
    """
    width = bank.shape[1]
    prev = _dp(query, bank, np.zeros(width + 1, dtype=np.int32))
    j = np.arange(width + 1)
    valid = j[None, :] <= lengths[:, None]
    return np.where(valid, prev, np.iinfo(np.int32).max).min(axis=1).astype(np.int64)


def edit_similarity_matrix(
    queries: list[np.ndarray], bank_sequences: list[np.ndarray]
) -> np.ndarray:
    """(len(queries), len(bank)) of 1 - normalised edit distance, in [0, 1]."""
    bank, lengths = pack(bank_sequences)
    out = np.empty((len(queries), len(bank_sequences)), dtype=np.float64)
    for i, q in enumerate(queries):
        d = edit_to_bank(q, bank, lengths)
        denom = np.maximum(np.maximum(lengths, len(q)), 1)
        out[i] = 1.0 - d / denom
    return out


def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    def unit(v):
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)
    return unit(a) @ unit(b).T


# --- corpus loading --------------------------------------------------------

def load_labels(root: Path) -> dict:
    return json.loads((root / "labels.json").read_text(encoding="utf-8"))["labels"]


def collect(folder: Path, labels: dict, kind: str) -> list[dict]:
    """Featurise a folder once. `label` is a scoring key, never an input."""
    items = []
    for path in sorted(folder.glob("*.wav")):
        record = labels.get(path.name)
        if record is None or record.get("item_kind") != kind:
            continue
        x, _ = features(load_wav(path))
        a, b = speech_span(x)
        items.append({
            "name": path.name,
            "label": record["item_id"],
            "base": record.get("base_rendering_id"),
            "frames": x,
            "speech": x[a:b],
        })
    if not items:
        raise ValueError(f"no {kind} audio in {folder}")
    return items


def encode_items(items: list[dict], centers: np.ndarray) -> dict:
    """Unit strings and unit histograms for a fixed codebook."""
    k = len(centers)
    sequences, histograms = [], np.zeros((len(items), k), dtype=np.float64)
    for i, it in enumerate(items):
        ids = encode(it["speech"], centers)
        sequences.append(collapse(ids))
        counts = np.bincount(ids, minlength=k).astype(np.float64)
        histograms[i] = counts / max(counts.sum(), 1.0)
    return {"sequences": sequences, "histograms": histograms}


# --- test 1: within vs between ---------------------------------------------

def separation(similarity: np.ndarray, labels: list[str], bases: list[str]) -> dict:
    """Within-syllable minus between-syllable similarity on a symmetric matrix.

    Same-base pairs are augmentation twins of one vocoder rendering, so they are
    reported apart from the honest number: `within_diff_base` compares two
    genuinely different utterances of the same syllable.
    """
    y = np.asarray(labels)
    b = np.asarray(bases)
    n = len(y)
    iu = np.triu_indices(n, k=1)
    s = similarity[iu]
    same_label = (y[:, None] == y[None, :])[iu]
    same_base = (b[:, None] == b[None, :])[iu]
    within_twin = s[same_label & same_base]
    within_diff = s[same_label & ~same_base]
    between = s[~same_label]

    def auc(pos: np.ndarray, neg: np.ndarray) -> float:
        """P(a within pair scores above a between pair); 0.5 is no information."""
        if not len(pos) or not len(neg):
            return float("nan")
        order = np.argsort(np.concatenate([pos, neg]), kind="stable")
        ranks = np.empty(len(order), dtype=np.float64)
        ranks[order] = np.arange(1, len(order) + 1)
        values = np.concatenate([pos, neg])
        # average ranks for ties so exact ties score 0.5
        _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
        sums = np.zeros(len(counts))
        np.add.at(sums, inverse, ranks)
        ranks = (sums / counts)[inverse]
        return float((ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2)
                     / (len(pos) * len(neg)))

    pooled = math.sqrt((within_diff.var() + between.var()) / 2) or 1e-12
    return {
        "within_same_syllable_diff_base": float(within_diff.mean()),
        "within_same_syllable_same_base_twins": float(within_twin.mean()) if len(within_twin) else None,
        "between_syllables": float(between.mean()),
        "separation": float(within_diff.mean() - between.mean()),
        "cohens_d": float((within_diff.mean() - between.mean()) / pooled),
        "auc": auc(within_diff, between),
        "pairs_within": int(len(within_diff)),
        "pairs_between": int(len(between)),
    }


# --- test 2: nearest neighbour ---------------------------------------------

def nn_classify(
    similarity: np.ndarray, train_labels: list[str], test_labels: list[str],
    classes: list[str], top_n: int = 5,
) -> dict:
    """1-NN over `classes`; each class is scored by its most similar train token."""
    index = {c: i for i, c in enumerate(classes)}
    train_ids = np.asarray([index[y] for y in train_labels])
    per_class = np.full((similarity.shape[0], len(classes)), -np.inf)
    mean_link = np.full((similarity.shape[0], len(classes)), -np.inf)
    for c in range(len(classes)):
        member = train_ids == c
        if member.any():
            per_class[:, c] = similarity[:, member].max(axis=1)
            mean_link[:, c] = similarity[:, member].mean(axis=1)
    ranking = np.argsort(-per_class, axis=1, kind="stable")
    truth = np.asarray([index[y] for y in test_labels])
    predicted = ranking[:, 0]
    # Average similarity to a whole class. With six training tokens per class a
    # single odd token can hijack 1-NN, so this is reported alongside it and any
    # claim that rests on only one of the two is not a claim.
    mean_predicted = mean_link.argmax(axis=1)
    confusion = np.zeros((len(classes), len(classes)), dtype=np.int64)
    np.add.at(confusion, (truth, predicted), 1)
    return {
        "classes": len(classes),
        "chance": 1.0 / len(classes),
        "top1": float(np.mean(predicted == truth)),
        f"top{top_n}": float(np.mean([truth[i] in ranking[i, :top_n]
                                      for i in range(len(truth))])),
        "meanlink_top1": float(np.mean(mean_predicted == truth)),
        "items": int(len(truth)),
        "confusion": confusion,
        "predicted": predicted,
        "meanlink_predicted": mean_predicted,
        "truth": truth,
    }


def permutation_null(
    similarity: np.ndarray, train_labels: list[str], test_labels: list[str],
    classes: list[str], seed: int, draws: int = 200,
) -> dict:
    """Empirical accuracy floor: same probe, held-out labels shuffled."""
    rng = np.random.default_rng(seed)
    scores = []
    for _ in range(draws):
        shuffled = list(rng.permutation(test_labels))
        scores.append(nn_classify(similarity, train_labels, shuffled, classes)["top1"])
    scores = np.asarray(scores)
    return {
        "draws": draws,
        "mean": float(scores.mean()),
        "p95": float(np.quantile(scores, 0.95)),
        "max": float(scores.max()),
    }


def top_confusions(confusion: np.ndarray, classes: list[str], limit: int = 12) -> list[dict]:
    """Most frequent off-diagonal errors, merged into unordered pairs."""
    merged: dict[tuple[str, str], int] = {}
    for i in range(len(classes)):
        for j in range(len(classes)):
            if i == j or confusion[i, j] == 0:
                continue
            key = tuple(sorted((classes[i], classes[j])))
            merged[key] = merged.get(key, 0) + int(confusion[i, j])
    ordered = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"pair": f"{a}/{b}", "errors": n} for (a, b), n in ordered[:limit]]


# --- test 3: minimal pairs -------------------------------------------------

MINIMAL_PAIRS = (
    ("ba", "pa"), ("ga", "ka"), ("da", "ta"), ("sa", "sha"),
    ("ka", "qa"), ("ta", "tha"), ("za", "sa"),
    # third pair that modern Hebrew genuinely merges; included so the homophone
    # controls are not just the two that happened to be on the original list
    ("ah", "aa"),
)


def binomial_tail(successes: int, trials: int, p: float = 0.5) -> float:
    """One-sided P(X >= successes) for X ~ Binomial(trials, p)."""
    total = 0.0
    for k in range(successes, trials + 1):
        total += math.comb(trials, k) * p ** k * (1 - p) ** (trials - k)
    return total


def minimal_pair_scores(
    similarity: np.ndarray, train_labels: list[str], test_labels: list[str],
) -> list[dict]:
    """Forced two-way choice restricted to the members of each close pair."""
    train = np.asarray(train_labels)
    test = np.asarray(test_labels)
    out = []
    for a, b in MINIMAL_PAIRS:
        train_mask = (train == a) | (train == b)
        test_mask = (test == a) | (test == b)
        if not train_mask.any() or not test_mask.any():
            continue
        sub = similarity[np.ix_(test_mask, train_mask)]
        result = nn_classify(sub, list(train[train_mask]), list(test[test_mask]),
                             [a, b], top_n=2)
        correct = int(round(result["top1"] * result["items"]))
        mean_correct = int(round(result["meanlink_top1"] * result["items"]))
        out.append({
            "pair": f"{a}/{b}",
            "accuracy": result["top1"],
            "meanlink_accuracy": result["meanlink_top1"],
            "correct": correct,
            "meanlink_correct": mean_correct,
            "items": result["items"],
            "p_value_vs_coinflip": binomial_tail(correct, result["items"]),
            "meanlink_p_value_vs_coinflip": binomial_tail(mean_correct, result["items"]),
        })
    return out


# --- test 4: words ---------------------------------------------------------

FINALS = {"ך": "כ", "ם": "מ", "ן": "נ",
          "ף": "פ", "ץ": "צ"}


def word_constituents(hebrew: str, glyph_to_syllable: dict[str, str]) -> list[str]:
    """Letters of a word mapped to the syllable ids the ant was taught."""
    out = []
    for character in hebrew:
        letter = FINALS.get(character, character)
        syllable = glyph_to_syllable.get(letter)
        if syllable is not None:
            out.append(syllable)
    return out


def constituent_recall(
    word_sequences: list[np.ndarray], word_labels: list[str],
    syllable_sequences: list[np.ndarray], syllable_labels: list[str],
    constituents: dict[str, list[str]], classes: list[str],
) -> dict:
    """Do a word's units contain its syllables' unit strings, above chance?

    For every word token each of the 22 syllables is aligned as a substring; the
    22 are then ranked. A syllable that really is in the word should rank high.
    Reported threshold-free, as an AUC over (constituent, non-constituent) pairs,
    because any absolute match rate depends on an arbitrary cut-off.
    """
    bank, lengths = pack(word_sequences)
    scores = np.zeros((len(word_sequences), len(classes)), dtype=np.float64)
    labels = np.asarray(syllable_labels)
    for c, syllable in enumerate(classes):
        best = np.full(len(word_sequences), -np.inf)
        for q in [syllable_sequences[i] for i in np.flatnonzero(labels == syllable)]:
            d = substring_edit_to_bank(q, bank, lengths)
            best = np.maximum(best, 1.0 - d / max(len(q), 1))
        scores[:, c] = best
    index = {c: i for i, c in enumerate(classes)}
    hits, ranks, pos, neg = [], [], [], []
    for row, word in enumerate(word_labels):
        member = {index[s] for s in constituents[word] if s in index}
        if not member:
            continue
        order = np.argsort(-scores[row], kind="stable")
        rank_of = {int(c): r for r, c in enumerate(order)}
        for c in range(len(classes)):
            (pos if c in member else neg).append(scores[row, c])
        for c in member:
            ranks.append(rank_of[c] / (len(classes) - 1))
            hits.append(rank_of[c] < len(member))
    pos_a, neg_a = np.asarray(pos), np.asarray(neg)
    auc = float(np.mean(pos_a[:, None] > neg_a[None, :])
                + 0.5 * np.mean(pos_a[:, None] == neg_a[None, :]))
    return {
        "word_tokens": len(word_sequences),
        "constituent_rank_percentile": float(np.mean(ranks)),
        "constituent_rank_percentile_chance": 0.5,
        "in_top_n_rate": float(np.mean(hits)),
        "in_top_n_rate_chance": float(np.mean(
            [len(set(constituents[w])) / len(classes) for w in word_labels])),
        "auc_constituent_over_other": auc,
    }


def leave_one_base_out(
    similarity: np.ndarray, labels: list[str], bases: list[str], classes: list[str],
) -> dict:
    """Rotate whole vocoder renderings out so augmentation twins cannot leak."""
    b = np.asarray(bases)
    folds = sorted({x.rsplit("/", 1)[-1] for x in bases})
    top1, top5, mean_link = [], [], []
    confusion = np.zeros((len(classes), len(classes)), dtype=np.int64)
    for fold in folds:
        test = np.asarray([x.endswith("/" + fold) for x in b])
        if not test.any() or test.all():
            continue
        sub = similarity[np.ix_(test, ~test)]
        result = nn_classify(sub, [l for l, t in zip(labels, test) if not t],
                             [l for l, t in zip(labels, test) if t], classes)
        top1.append(result["top1"])
        top5.append(result["top5"])
        mean_link.append(result["meanlink_top1"])
        confusion += result["confusion"]
    return {
        "classes": len(classes),
        "chance": 1.0 / len(classes),
        "folds": len(top1),
        "top1": float(np.mean(top1)),
        "top5": float(np.mean(top5)),
        "meanlink_top1": float(np.mean(mean_link)),
        "confusion": confusion,
    }
