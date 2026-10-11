"""Package an explicit source manifest. Never include runtimes or user data."""
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from version import VERSION

FILES = [
    "app.py", "desktop.py", "glass.py", "scrobbler.py", "version.py", "build.py", "requirements.txt", "requirements-build.txt",
    "README.md", "LICENSE", "THIRD-PARTY-NOTICES.txt",
    "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "CODE_OF_CONDUCT.md",
    "assets/app.png", "assets/app.ico", "assets/branding/achilleus-black.png", "assets/branding/achilleus-white.png", "assets/branding/achilleus-white-small.png",
    "assets/shaders/vertex.vert", "assets/shaders/environment.frag", "assets/shaders/glass.frag", "assets/shaders/copy.frag",
    "licenses/Qt-LGPL-3.0.txt", "licenses/Qt-GPL-3.0.txt", "licenses/Qt-THIRD-PARTY.txt",
    "licenses/TclTk-LICENSE.txt", "licenses/OpenSSL-LICENSE.txt", "licenses/libffi-LICENSE.txt",
    "licenses/zlib-LICENSE.txt", "licenses/bzip2-LICENSE.txt", "licenses/xz-LICENSE.txt", "licenses/libmpdec-LICENSE.txt",
    "docs/images/preview.png", "docs/images/preview-dark.png",
    "tests/test_scrobbler.py", "tests/test_desktop.py", "tools/package_release.py", "tools/build_installer.py", "tools/render_preview.py",
    ".gitignore", ".gitattributes", ".github/workflows/checks.yml", ".github/workflows/release.yml",
    ".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/config.yml", ".github/PULL_REQUEST_TEMPLATE.md",
    "docs/USER_GUIDE.md", "docs/TROUBLESHOOTING.md", "docs/ARCHITECTURE.md", "docs/DISTRIBUTION.md",
    "docs/PORTABLE.txt", "docs/releases/1.1.0.md", "docs/releases/1.1.1.md", "docs/releases/1.2.0.md", "installer/setup.iss",
]


def main():
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Missing release files: " + ", ".join(missing))
    destination = ROOT / "dist"
    destination.mkdir(exist_ok=True)
    output = destination / f"Akis-Rockbox-Scrobbler-{VERSION}-source.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in FILES:
            archive.write(ROOT / name, "Akis-Rockbox-Scrobbler/" + name)
    print(f"Created {output.name} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
