"""Compile a per-user installer from the already-built portable app."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import VERSION


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iscc", type=Path)
    args = parser.parse_args()
    compiler = args.iscc or shutil.which("iscc")
    if not compiler:
        for directory in ("C:/Program Files (x86)/Inno Setup 6", "C:/Program Files/Inno Setup 6"):
            if (Path(directory) / "ISCC.exe").is_file():
                compiler = Path(directory) / "ISCC.exe"
                break
    if not compiler:
        raise SystemExit("Install Inno Setup 6 or supply --iscc PATH.")
    payload = ROOT / "dist" / "Akis-Rockbox-Scrobbler"
    if not (payload / "Akis-Rockbox-Scrobbler.exe").is_file():
        raise SystemExit("Run python build.py first.")
    subprocess.run([str(compiler), "/DAppVersion=" + VERSION, "/DPayloadDir=" + str(payload),
                    str(ROOT / "installer" / "setup.iss")], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
