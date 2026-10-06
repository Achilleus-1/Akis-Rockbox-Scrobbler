# GitHub upload preparation

Suggested repository: `Achilleus-1/Akis-Rockbox-Scrobbler`

Description: **Aki's Rockbox Scrobbler — Product of Achilleus. A lightweight local Rockbox-to-Last.fm importer with a Frutiger Aero interface.**

The local project contains the application, supplied Achilleus logos, README and preview, MIT license, contribution/security guidance, tests, CI, and an explicit source ZIP packager. Personal queues, account credentials, launch tokens, listening logs, and test tools are excluded from Git and release archives.

## Authenticate with GitHub CLI

Use an official installation of `gh`. A portable copy used for preparation is in `.test-data/tools/gh/bin/gh.exe`, which is ignored by Git.

```powershell
gh auth login --hostname github.com --git-protocol https --web
gh api user --jq .login
```

Confirm the returned account is the intended owner. Do not put tokens into scripts or command arguments. Git credentials are not copied into GitHub CLI during this preparation.

## Publish when ready

Review the prepared files and choose repository visibility. The command below creates a public repository and pushes the local `main` branch; use `--private` instead if wanted. Do not run it until the upload is intended.

```powershell
gh repo create Achilleus-1/Akis-Rockbox-Scrobbler --public --source . --remote origin --description "Aki's Rockbox Scrobbler — Product of Achilleus. A lightweight local Rockbox-to-Last.fm importer with a Frutiger Aero interface." --push
gh repo edit Achilleus-1/Akis-Rockbox-Scrobbler --homepage https://linktr.ee/achilleus_ --add-topic rockbox --add-topic lastfm --add-topic scrobbler --add-topic frutiger-aero --add-topic python
```

If that repository already exists, inspect it first. Add its remote and push normally only if it is the intended destination; do not replace unrelated history or force-push.

## Optional source release

```powershell
python tools/package_release.py
gh release create v1.0.0 dist/Akis-Rockbox-Scrobbler-1.0.0.zip --repo Achilleus-1/Akis-Rockbox-Scrobbler --target main --title "Aki's Rockbox Scrobbler 1.0.0" --notes-file CHANGELOG.md
```

The ZIP requires Python and is not a packaged executable. GitHub's automatic source downloads also include the repository. Verify the CI result after publishing; local checks cannot confirm a remote workflow run before upload.
