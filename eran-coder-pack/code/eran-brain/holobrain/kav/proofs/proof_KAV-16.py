"""KAV-16 proof — the 2026-09-05 body of work has provenance outside the working tree

Run: python proofs/proof_KAV-16.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-16.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import hashlib, io, json
    rec = r"D:\CLAUDE\_deliverables\code-revision\kav-proofs\PROVENANCE-kav-20260906.json"
    assert os.path.exists(rec), (
        "joiner.py, ruler.py and tests/test_joiner.py are modified and uncommitted; the "
        "last commit touching them is 39d9b8968 (2026-09-03). The fold, the grove, "
        "measure_join_wide and the whole GATE2_DECISION_20260905 record exist only on "
        "disk, and there is no provenance for the numbers Iddo's memory now cites.")
    prov = json.load(io.open(rec, encoding="utf-8"))

    def sha(path):
        h = hashlib.sha256()
        h.update(io.open(path, "rb").read())
        return h.hexdigest()

    for f in ("joiner.py", "ruler.py", "tests/test_joiner.py"):
        assert f in prov["files"], f
        live = os.path.join(organ, f.replace("/", os.sep))
        got, want = sha(live), prov["files"][f]["sha256"]
        print(f"    {f}: on disk {got[:16]}...  recorded {want[:16]}...")
        assert got == want, (
            f"{f} on disk is NOT the file the provenance record names. The 2026-09-05 "
            f"body of work is uncommitted -- the last commit touching these three is "
            f"39d9b8968 (2026-09-03) -- so a record that does not match the disk is no "
            f"provenance at all.")
    assert prov.get("wide_table"), "the measured wide table is not recorded with them"
    print(f"    wide table recorded: {prov['wide_table']['accuracy']} / "
          f"{prov['wide_table']['right_solids']} over "
          f"{prov['wide_table']['questions']} questions")
    print(f"    committed={prov.get('committed')}  note={prov.get('note', '')[:70]}")


_harness.run(check)
