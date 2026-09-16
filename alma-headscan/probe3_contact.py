# probe3_contact.py - contact sheet of all 60 keyframes to see orbit coverage with eyes.
import glob, os
import numpy as np
import cv2

SCRATCH = r"C:\Users\<user>\AppData\Local\Temp\claude\D--CLAUDE\19ebf17c-40e0-4c38-9292-d19f3347d92e\scratchpad"
FRAMES = sorted(glob.glob(os.path.join(SCRATCH, "frames", "k*.jpg")))
tw, th = 135, 240  # portrait thumbs
cols, rows = 10, 6
sheet = np.zeros((rows * th, cols * tw, 3), np.uint8)
for n, fp in enumerate(FRAMES):
    img = cv2.imread(fp)
    t = cv2.resize(img, (tw, th))
    cv2.putText(t, str(n), (4, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
    r, c = divmod(n, cols)
    sheet[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
out = os.path.join(SCRATCH, "probe3_contact_sheet.jpg")
cv2.imwrite(out, sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
print("wrote", out, sheet.shape)
