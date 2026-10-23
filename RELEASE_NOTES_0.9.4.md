# RaTracker v0.9.4

- Increased synthesized sound volume (master compressor limits peaks).
- Adjusted bulb pull cord anchoring and length.
- Fixed Windows backup PowerShell parser error `${LASTEXITCODE}:`.
- Fixed Git metadata lookup for ZIP deployments without `.git`.
- Static asset cache version bumped.

No database migrations. Windows backup still requires Docker Desktop and running `db`/`web` services.
