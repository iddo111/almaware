"""MIKO v1 -- one-shot migration: positional ram: ids -> content-addressed ids.

Code revision 2026-09-06, defect MIKO-06. Run ONCE; it is idempotent (re-running finds
nothing to do). It changes ONLY the `id` label of RAMCHAT documents -- not one character of
any query, text, embedding or target.

Why: `ram:{i:04d}` was the index into ramchat_session.json, a rolling 500-message window.
Every rebuild silently pointed those ids at whatever message currently sat at that index --
verified on 2026-09-06: all five ram: exam targets had drifted onto different messages
(ram:0347 snapshot at=14:10 vs live raw[347] at=00:00, and so on). No error was ever raised
because the ids still "existed".

What it rewrites, each backed up as <file>.bak-rev-20260906 by the revision pass:
    corpus.jsonl        the id field of every ram: document
    split.json          train/val/test id lists
    exam.json           target_id of the five ram: exam questions
    e5_doc_emb.pt       the "ids" list (embeddings untouched, order untouched)
    e5_query_emb.pt     the "ids" list
    e5_exam_emb.pt      the "targets" list

New id = "ram:" + sha1(query + "\\n" + text)[:12] -- computable identically from a frozen
corpus document and from a fresh build_corpus.py run, which is what makes the migration
mechanical and a future rebuild stable.
"""
from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def main(apply: bool = True) -> dict:
    from build_corpus import ram_doc_id

    docs = [json.loads(l) for l in (HERE / "corpus.jsonl").open(encoding="utf-8")]
    mapping: dict[str, str] = {}
    for d in docs:
        if d["id"].startswith("ram:"):
            mapping[d["id"]] = ram_doc_id(d["query"], d["text"])

    already = all(old == new for old, new in mapping.items())
    if already:
        print("nothing to do -- ram: ids are already content-addressed")
        return {"migrated": 0}

    assert len(set(mapping.values())) == len(mapping), "id collision in the new hashes"
    print(f"ram documents: {len(mapping)}; new ids unique: {len(set(mapping.values()))}")

    if not apply:
        return {"migrated": 0, "would_migrate": len(mapping)}

    # 1. corpus.jsonl -- rewrite ONLY the id field, preserving order and every other byte
    with (HERE / "corpus.jsonl").open("w", encoding="utf-8") as f:
        for d in docs:
            d["id"] = mapping.get(d["id"], d["id"])
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    print(f"corpus.jsonl: {len(mapping)} ram ids rewritten")

    # 2. split.json
    split = json.loads((HERE / "split.json").read_text(encoding="utf-8"))
    n_split = 0
    for key in ("train", "val", "test"):
        new_list = []
        for i in split[key]:
            if i in mapping:
                n_split += 1
            new_list.append(mapping.get(i, i))
        split[key] = sorted(new_list)
    (HERE / "split.json").write_text(json.dumps(split, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
    print(f"split.json: {n_split} ids rewritten")

    # 3. exam.json
    exam = json.loads((HERE / "exam.json").read_text(encoding="utf-8"))
    n_exam = 0
    for e in exam:
        if e["target_id"] in mapping:
            e["target_id"] = mapping[e["target_id"]]
            n_exam += 1
    (HERE / "exam.json").write_text(json.dumps(exam, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")
    print(f"exam.json: {n_exam} target ids rewritten")

    # 4. the cached e5 packs -- id LISTS only; the tensors are not touched
    import torch
    for name, key in (("e5_doc_emb.pt", "ids"), ("e5_query_emb.pt", "ids"),
                      ("e5_exam_emb.pt", "targets")):
        path = HERE / name
        if not path.exists():
            continue
        pack = torch.load(path, weights_only=False)
        before = list(pack[key])
        pack[key] = [mapping.get(i, i) for i in before]
        n = sum(1 for a, b in zip(before, pack[key]) if a != b)
        torch.save(pack, path)
        print(f"{name}: {n} ids rewritten in '{key}'")

    (HERE / "ram_id_migration.json").write_text(
        json.dumps({"note": "MIKO-06 positional -> content-addressed ram ids, 2026-09-06",
                    "mapping": mapping}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote the old->new map -> {HERE / 'ram_id_migration.json'}")
    return {"migrated": len(mapping)}


if __name__ == "__main__":
    main()
