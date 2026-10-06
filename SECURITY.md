# Security

For sensitive security reports, contact the maintainer through [Achilleus's profile](https://github.com/Achilleus-1) or [contact links](https://linktr.ee/achilleus_). If the GitHub repository offers private vulnerability reporting, use its Security tab. Do not post working secrets or private listening history in a public issue.

Include the affected version, operating system and Python version, reproduction steps using synthetic data, and the expected impact. Remove API keys, shared secrets, session tokens, authenticated launch URLs, and local database contents from screenshots or attachments.

The local server must stay bound to loopback, validate Host/Origin/CSRF/session checks, serve only known assets, and retain TLS certificate verification for Last.fm. Windows DPAPI protects remembered credentials for the current Windows user; source logs are never modified. This project has not received an independent security audit.
