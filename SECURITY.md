# Security

For sensitive security reports, use the repository's [private vulnerability reporting page](https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler/security/advisories/new) when available, or contact the maintainer through [Achilleus's contact links](https://linktr.ee/achilleus_). Do not post working secrets or private listening history in a public issue.

## Supported releases

Security fixes are applied to the latest published release and the `main` branch. Upgrade to the latest release before reporting a problem in an older version. There is no guaranteed response or patch schedule.

## Reporting details

Include the affected version, operating system and Python version, reproduction steps using synthetic data, and the expected impact. Remove API keys, shared secrets, session tokens, authenticated launch URLs, and local database contents from screenshots or attachments.

The local server must stay bound to loopback, validate Host/Origin/CSRF/session checks, serve only known assets, and retain TLS certificate verification for Last.fm. Windows DPAPI protects remembered credentials for the current Windows user; source logs are never modified. This project has not received an independent security audit.
