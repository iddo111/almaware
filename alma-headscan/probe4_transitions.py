# probe4_transitions.py - can SIFT+RANSAC bridge the view-cluster transitions directly?
import glob, os, json
import numpy as np
import cv2

SCRATCH = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\19ebf17c-40e0-4c38-9292-d19f3347d92e\scratchpad"
FRAMES = sorted(glob.glob(os.path.join(SCRATCH, "frames", "k*.jpg")))
W, H = 1080, 1920
sift = cv2.SIFT_create(nfeatures=6000)
bf = cv2.BFMatcher()
cache = {}
def sp(i):
    if i not in cache:
        g = cv2.cvtColor(cv2.imread(FRAMES[i]), cv2.COLOR_BGR2GRAY)
        cache[i] = sift.detectAndCompute(g, None)
    return cache[i]

def pair_stat(ia, ib):
    kA, dA = sp(ia); kB, dB = sp(ib)
    m = bf.knnMatch(dA, dB, k=2)
    good = [x for x, y in m if x.distance < 0.8 * y.distance]
    if len(good) < 8:
        return {"pair": (ia, ib), "ratio_matches": len(good), "F_inliers": 0}
    ptsA = np.float32([kA[g.queryIdx].pt for g in good])
    ptsB = np.float32([kB[g.trainIdx].pt for g in good])
    F, mask = cv2.findFundamentalMat(ptsA, ptsB, cv2.FM_RANSAC, 2.0, 0.999)
    inl = int(mask.sum()) if mask is not None else 0
    return {"pair": (ia, ib), "ratio_matches": len(good), "F_inliers": inl}

transitions = [(15, 16), (16, 17), (17, 18), (19, 20), (21, 22), (25, 30), (33, 34),
               (35, 36), (36, 37), (37, 38), (16, 22), (20, 21), (19, 22), (17, 25),
               (36, 30), (37, 33)]
out = [pair_stat(a, b) for a, b in transitions]
print(json.dumps(out, indent=1))
