Security policy

If you discover a vulnerability in this project, please disclose it privately to the maintainer (Chris HaPunkt) by opening an issue marked as "private" or by contacting the project owner directly. Do not publish sensitive details publicly until a fix is available.

Handling credentials
- Never commit real credentials (passwords, tokens, API keys) to this repository.
- For development and tests, use environment variables or a local secrets file that is listed in .gitignore (tests/secrets.py).
- Rotate any tokens or passwords that were accidentally committed.

Reporting
- Provide a minimal reproducible example and steps to reproduce.
- If the issue includes leaked credentials, list which accounts may be affected.