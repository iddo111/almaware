"""KAV-15 proof — the run leg can write the artifact the render track reads

Run: python proofs/proof_KAV-15.py old   -> must FAIL (exit 1)
     python proofs/proof_KAV-15.py new   -> must PASS (exit 0)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness


def check(organ):

    import glob, io, json, tempfile
    import mesh, ruler
    assert hasattr(ruler, "say_to_file"), (
        "no code in the repository can write kav/KAV-first-shape.stl -- mesh.write_stl "
        "has zero callers in all of holobrain -- so the only artifact KAV hands tzelem "
        "and einayim is stale (2026-09-02, before the vertex-index rebuild) and "
        "unregenerable")
    out = os.path.join(tempfile.mkdtemp(prefix="kav-say-"), "KAV-cube.stl")
    info = ruler.say_to_file("cube", out)
    print("    " + json.dumps({k: info[k] for k in
                               ("shape", "chain", "said_faces", "true_faces",
                                "watertight", "volume_ratio", "right_solid",
                                "corpus")}, ensure_ascii=False))
    assert os.path.exists(out) and os.path.getsize(out) > 84
    side = os.path.splitext(out)[0] + ".json"
    assert os.path.exists(side), "no sidecar: the artifact cannot name the run that made it"
    back = mesh.read_stl(out)
    g = mesh.geometry(back)
    print(f"    wrote {os.path.getsize(out)} bytes, {len(back)} faces, "
          f"watertight={g['watertight']}")
    assert g["watertight"] and len(back) == info["true_faces"]


_harness.run(check)
