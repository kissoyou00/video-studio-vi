"""Patch SadTalker (commit cd4c046) to run with numpy 1.26 / torch 2.8 and without the optional
face enhancer (gfpgan/basicsr). Idempotent: run by install_talker.ps1 after every checkout.
Usage: python patch_sadtalker.py <sadtalker folder>"""
import sys
from pathlib import Path

root = Path(sys.argv[1])
PATCHES = [
    ("src/face3d/util/my_awing_arch.py", "preds.astype(np.float, copy=False)", "preds.astype(np.float64, copy=False)"),
    # numpy >= 1.24 refuses to build an array from a mix of scalars and 1-element arrays
    ("src/face3d/util/preprocess.py", "trans_params = np.array([w0, h0, s, t[0], t[1]])",
     "trans_params = np.array([float(np.squeeze(v)) for v in (w0, h0, s, t[0], t[1])])"),
    # the GFPGAN enhancer is optional and its basicsr dependency does not install on new Pythons
    ("src/facerender/animate.py", "from src.utils.face_enhancer import enhancer_generator_with_len, enhancer_list",
     "try:\n    from src.utils.face_enhancer import enhancer_generator_with_len, enhancer_list\nexcept ImportError:\n"
     "    enhancer_generator_with_len = enhancer_list = None"),
]

for rel, old, new in PATCHES:
    p = root / rel
    text = p.read_text(encoding="utf-8")
    if new in text:
        continue
    if old not in text:
        sys.exit(f"patch_sadtalker: pattern not found in {rel}; SadTalker version changed?")
    p.write_text(text.replace(old, new), encoding="utf-8")
    print("patched", rel)
