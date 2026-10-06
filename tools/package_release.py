"""Create a source ZIP from an explicit list, without personal data or dependencies."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '1.0.0'
FILES = [
    'scrobbler.py', 'Start Akis Rockbox Scrobbler.cmd', 'README.md', 'LICENSE',
    'CONTRIBUTING.md', 'SECURITY.md', 'CHANGELOG.md',
    'web/index.html', 'web/app.js', 'web/liquid-glass.js', 'web/style.css',
    'web/logo-black.png', 'web/logo-white.png', 'docs/images/preview.png',
    'tests/test_scrobbler.py', 'tests/test_liquid_glass.cjs', 'tools/package_release.py', '.gitignore',
    '.github/workflows/checks.yml', '.gitattributes', 'PUBLISHING.md',
]


def main():
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit('Missing release files: ' + ', '.join(missing))
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    output = destination / f'Akis-Rockbox-Scrobbler-{VERSION}.zip'
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in FILES:
            archive.write(ROOT / name, f'Akis-Rockbox-Scrobbler/{name}')
    print(f'Created {output.name} ({output.stat().st_size:,} bytes, {len(FILES)} files)')


if __name__ == '__main__':
    main()
