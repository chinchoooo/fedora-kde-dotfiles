#!/usr/bin/env python3
"""RECONSTRUCTION of how a greyscale icon theme can be derived from Gruvbox-Plus-Dark (the committed repo does not ship the 217 MB theme).
Copies ~/.local/share/icons/Gruvbox-Plus-Dark to Mono-Plus-Dark and replaces every #rrggbb in the SVGs by its luminance grey.
The original Mono-Plus-Dark on the machine was made the same way in spirit; this script is untested against it byte for byte."""
import re, shutil, sys
from pathlib import Path

src = Path.home() / ".local/share/icons/Gruvbox-Plus-Dark"
dst = Path.home() / ".local/share/icons/Mono-Plus-Dark"
if not src.exists():
    sys.exit("install Gruvbox-Plus-Dark first (https://github.com/SylEleuth/gruvbox-plus-icon-pack)")
shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)

def grey(m):
    r, g, b = (int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4))
    y = round(0.299 * r + 0.587 * g + 0.114 * b)
    return "#%02x%02x%02x" % (y, y, y)

for f in dst.rglob("*.svg"):
    if f.is_symlink():
        continue
    t = f.read_text(errors="ignore")
    f.write_text(re.sub(r"#([0-9a-fA-F]{6})\b", grey, t))
idx = dst / "index.theme"
idx.write_text(re.sub(r"(?m)^Name=.*$", "Name=Mono-Plus-Dark", idx.read_text(), count=1))
print("done; run: kbuildsycoca6 && plasma-apply-colorscheme MonoDark")
