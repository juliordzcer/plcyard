"""Build the web version: `python -m plcyard.webbuild OUT_DIR` writes the page (web/), the design tokens
as CSS, the fonts and plcyard.zip (the Qt-free Python the page runs with Pyodide) into OUT_DIR."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path

PKG = Path(__file__).resolve().parent
WEB = PKG.parent / "web"
ASSETS = PKG / "ui" / "assets"
# what the browser needs: everything but the Qt user interface
PYTHON = ["__init__.py", "webapp.py", "webmachines.py", "grader.py", "labs.py", "core", "sims", "formats",
          "ui/__init__.py", "ui/ladder_layout.py", "ui/notation.py"]
DATA = ["data/labs", "data/samples"]


def tokens_css() -> str:
    light = json.loads((ASSETS / "tokens.light.json").read_text(encoding="utf-8"))["color"]
    dark = json.loads((ASSETS / "tokens.dark.json").read_text(encoding="utf-8"))["color"]
    block = lambda c: "\n".join(f"  --{k}: {v};" for k, v in c.items())
    return (f":root {{\n  color-scheme: light dark;\n{block(light)}\n}}\n"
            f"@media (prefers-color-scheme: dark) {{\n  :root:not([data-theme=\"light\"]) {{\n{block(dark)}\n  }}\n}}\n"
            f":root[data-theme=\"dark\"] {{\n{block(dark)}\n}}\n")


def python_zip(path: Path) -> int:
    files = 0
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for item in PYTHON + DATA:
            src = PKG / item
            for f in ([src] if src.is_file() else sorted(src.rglob("*"))):
                if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc":
                    info = zipfile.ZipInfo(str(Path("plcyard") / f.relative_to(PKG)), (2020, 1, 1, 0, 0, 0))
                    z.writestr(info, f.read_bytes(), zipfile.ZIP_DEFLATED)   # no timestamps: same input, same zip
                    files += 1
    return files


def build(out: Path) -> None:
    """Every file the page loads carries ?v=<hash of the build>, so browsers fetch a new release at
    once; version.json lets an open tab notice it."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "tokens.css").write_text(tokens_css(), encoding="utf-8")
    shutil.copy2(ASSETS / "icon.svg", out / "icon.svg")
    fonts = out / "fonts"
    fonts.mkdir(exist_ok=True)
    for f in (ASSETS / "fonts").iterdir():
        shutil.copy2(f, fonts / f.name)
    n = python_zip(out / "plcyard.zip")
    digest = hashlib.sha256()
    for f in sorted(WEB.iterdir()):
        if f.is_file():
            digest.update(f.read_bytes())
    for f in ("tokens.css", "plcyard.zip"):
        digest.update((out / f).read_bytes())
    version = digest.hexdigest()[:12]
    for f in WEB.iterdir():
        if f.is_file():
            text = f.read_text(encoding="utf-8")
            (out / f.name).write_text(text.replace("__VERSION__", version), encoding="utf-8")
    (out / "version.json").write_text(json.dumps({"version": version}) + "\n", encoding="utf-8")
    print(f"web version in {out} ({n} files in plcyard.zip)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m plcyard.webbuild OUT_DIR")
    build(Path(sys.argv[1]))
