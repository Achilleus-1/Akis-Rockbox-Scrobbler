# Security

Use the repository's [private vulnerability reporting page](https://github.com/Achilleus-1/Akis-Rockbox-Scrobbler/security/advisories/new) when available, or [Achilleus's contact links](https://linktr.ee/achilleus_). Do not post working credentials or private listening history in public issues.

Security fixes apply to the latest published release and `main`. Include the app version, operating system, install/portable/source edition, a synthetic reproduction and expected impact. Remove API keys, shared secrets, session keys and databases from attachments.

The app is native and starts no HTTP listener. Last.fm requests must retain HTTPS certificate verification, reject redirects, and avoid exposing secrets in errors. Windows DPAPI protects saved credentials for the current Windows user. Source logs are never modified. Submissions require explicit selection, account/date confirmation, durable receipts and uncertain-outcome handling.

Release builds must include dependency notices and exclude private data. The app has not received an independent security audit.
