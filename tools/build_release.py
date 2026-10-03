"""Build the release zip of the skill and its SHA256SUMS. Standard library only.

    python tools/build_release.py

The zip holds the skill folder (audit/) as claude.ai and npx skills expect. It is
reproducible: fixed file dates, sorted entries and LF line endings, so anyone can
rebuild it from the tagged source and get the same checksum.
"""
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "backpack-skill"
SKILL = PLUGIN / "skills" / "audit"
DIST = ROOT / "dist"
TEXT = {".py", ".md", ".html", ".json", ".txt"}
EPOCH = (1980, 1, 1, 0, 0, 0)  # earliest date a zip can hold


def files():
    for path in sorted(SKILL.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            yield path


def build():
    version = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    DIST.mkdir(exist_ok=True)
    zip_path = DIST / f"backpack-skill-audit-{version}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files():
            data = path.read_bytes()
            if path.suffix in TEXT:
                data = data.replace(b"\r\n", b"\n")  # Windows checkouts add CR; keep the zip the same everywhere
            info = zipfile.ZipInfo("audit/" + path.relative_to(SKILL).as_posix(), EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (DIST / "SHA256SUMS.txt").write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")
    return zip_path, digest


if __name__ == "__main__":
    path, digest = build()
    print(f"{path.name}\n{digest}")
