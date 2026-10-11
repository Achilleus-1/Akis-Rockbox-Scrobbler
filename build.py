"""Build the Windows EXE with private Python and replaceable Qt shared libraries."""
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
import ssl
import sqlite3
import zlib
import zipfile

from version import VERSION

ROOT = Path(__file__).resolve().parent
NAME = "Akis-Rockbox-Scrobbler"


def main():
    if sys.platform != "win32":
        raise SystemExit("Build Windows releases on Windows with x64 Python.")
    if sys.maxsize <= 2**32:
        raise SystemExit("Windows releases require x64 Python.")
    if sys.version_info < (3, 12) or not ssl.OPENSSL_VERSION.startswith("OpenSSL 3."):
        raise SystemExit("Windows release builds require Python 3.12+ with OpenSSL 3.")
    licenses = ROOT / "build" / "licenses"
    licenses.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(Path(sys.base_prefix) / "LICENSE.txt", licenses / "Python-LICENSE.txt")
    distribution = importlib.metadata.distribution("PyInstaller")
    copying = next(file for file in distribution.files if str(file).endswith("licenses/COPYING.txt"))
    shutil.copyfile(distribution.locate_file(copying), licenses / "PyInstaller-COPYING.txt")
    for path in sorted((ROOT / "licenses").glob("*.txt")):
        shutil.copyfile(path, licenses / path.name)
    (licenses / "RUNTIME-VERSIONS.json").write_text(json.dumps({
        "python": sys.version, "openssl": ssl.OPENSSL_VERSION,
        "sqlite": sqlite3.sqlite_version, "zlib": zlib.ZLIB_RUNTIME_VERSION,
        "pyinstaller": distribution.version,
        "pyside6_essentials": importlib.metadata.version("PySide6_Essentials"),
    }, indent=2), encoding="utf-8")
    for name in ("LICENSE", "THIRD-PARTY-NOTICES.txt"):
        shutil.copyfile(ROOT / name, licenses / name)
    numeric_version = tuple(int(part) for part in VERSION.split(".")) + (0,)
    version_file = ROOT / "build" / "version-info.txt"
    version_file.write_text(f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numeric_version!r}, prodvers={numeric_version!r},
                   mask=0x3f, flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Achilleus'),
    StringStruct('FileDescription', "Aki's Rockbox Scrobbler"),
    StringStruct('FileVersion', '{VERSION}'),
    StringStruct('ProductName', "Aki's Rockbox Scrobbler"),
    StringStruct('ProductVersion', '{VERSION}'),
    StringStruct('OriginalFilename', '{NAME}.exe'),
    StringStruct('LegalCopyright', 'Copyright (c) 2026 Achilleus')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
''', encoding="utf-8")
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
               "--noupx", "--name", NAME, "--icon", str(ROOT / "assets" / "app.ico"),
               "--exclude-module", "tkinter", "--exclude-module", "PySide6.QtQml",
               "--exclude-module", "PySide6.QtQuick", "--exclude-module", "PySide6.QtWebEngineCore",
               "--version-file", str(version_file),
               "--specpath", str(ROOT / "build"), "--distpath", str(ROOT / "dist"),
               "--workpath", str(ROOT / "build" / "pyinstaller"),
               "--add-data", str(ROOT / "assets") + ";assets",
               "--add-data", str(licenses) + ";licenses", str(ROOT / "app.py")]
    # Do not accidentally collect DLLs from unrelated software on the developer's PATH.
    import os
    environment = os.environ.copy()
    windows = Path(os.environ.get("SystemRoot", "C:/Windows"))
    environment["PATH"] = os.pathsep.join([str(Path(sys.base_prefix)), str(windows / "System32"), str(windows)])
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    output = ROOT / "dist" / NAME
    shutil.copytree(licenses, output / "licenses", dirs_exist_ok=True)
    shutil.copyfile(ROOT / "docs" / "PORTABLE.txt", output / "README.txt")
    # Source downloads build the same EXE launcher directly in the project folder.
    runtime = ROOT / "_internal"
    if runtime.exists():
        if runtime.resolve() != ROOT.resolve() / "_internal" or not runtime.is_dir():
            raise SystemExit("Refusing to replace a runtime outside this project.")
        shutil.rmtree(runtime)
    shutil.copytree(output / "_internal", runtime)
    shutil.copyfile(output / (NAME + ".exe"), ROOT / (NAME + ".exe"))
    archive_path = ROOT / "dist" / f"{NAME}-{VERSION}-windows-x64-portable.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                archive.write(path, Path(NAME) / path.relative_to(output))
    print(f"Built {output / (NAME + '.exe')}")
    print(f"Local launcher: {ROOT / (NAME + '.exe')}")
    print(f"Portable release: {archive_path}")


if __name__ == "__main__":
    main()
