# Release process

Repository: [Achilleus-1/Akis-Rockbox-Scrobbler](https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler)

This guide is for maintainers. Normal users should download a release and follow the [user guide](docs/USER_GUIDE.md). Use Git and GitHub CLI for publishing.

## Before a release

1. Update `CHANGELOG.md`, the version in `tools/package_release.py`, and the app's visible version/User-Agent when the version changes. Keep README download links current.
2. Run all checks from [CONTRIBUTING.md](CONTRIBUTING.md) and verify the browser UI with an isolated test queue.
3. Commit the final source, push `main`, and wait for all CI jobs to pass.
4. Build the release from that clean checkout:

```powershell
python tools/package_release.py
```

The packager uses an explicit file list. Its ZIP contains source, assets, documentation and tests, with no personal queue, credentials, launch tokens, listening logs or development tools. It also writes `dist/SHA256SUMS.txt`. Do not add local data to that list.

## Authenticate

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh api user --jq .login
```

Verify the intended maintainer account. Never put tokens into command arguments, commits or release notes. If using an existing Git login instead, obtain the user's explicit authorization and keep its credential in process memory only.

## Tag and publish

For the 1.0.0 release:

```powershell
git tag -a v1.0.0 -m "Aki's Rockbox Scrobbler 1.0.0"
git push origin v1.0.0
gh release create v1.0.0 dist/Akis-Rockbox-Scrobbler-1.0.0.zip dist/SHA256SUMS.txt --repo Achilleus-1/Akis-Rockbox-Scrobbler --verify-tag --title "Aki's Rockbox Scrobbler 1.0.0" --notes-file CHANGELOG.md
```

Use the new version in all commands for subsequent releases. Do not replace an existing tag or release asset silently. Verify the release URL, uploaded assets, checksum and workflow result after publishing.

The ZIP is a source distribution requiring Python 3.10 or newer, not a bundled Windows executable. GitHub also provides automatic source archives.

## Verify a downloaded archive

On Windows:

```powershell
Get-FileHash .\Akis-Rockbox-Scrobbler-1.0.0.zip -Algorithm SHA256
```

Compare its hash with the matching line in `SHA256SUMS.txt`. A checksum detects changed or damaged downloads; it is not an independent security audit or signature.

## Repository configuration

Keep issues enabled with the supplied bug and feature forms. Use the security policy for private vulnerability reports. The README links to user documentation, CI and releases. Repository topics describe Rockbox, Last.fm, Python, scrobbling, Frutiger Aero and liquid glass; the homepage points to Achilleus's contact page.
