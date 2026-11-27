# Krillion Answers operations

Public operational scripts and question metadata only. No website source, deployments, DNS credentials, answers, or official guides.

- `ops.py health`: read all sitemap URLs, HTTP status, title, canonical and noindex; alert through GitHub Issues.
- `ops.py indexnow`: diff URL/lastmod against the last accepted snapshot; submit only new/changed URLs. Verify the existing on-host key file first. HTTP 429 retains the queue; Actions retries once after 45 minutes. A second 429 stays pending and opens an informational issue, never counts as accepted.
- `ops.py archive`: GET `https://krillion.io/api/today` with default Python headers and no login/browser. Save unmodified `prompts[].text` plus IDs, fetchedAt, date, dayNumber, resetsAt and sourceUrl to `latest.json` and `history/YYYY-MM-DD.json`. The date is the Dive's start-date label; the reset is **05:00 UTC**, not midnight. A rerun of the same dayNumber replaces its existing date file. The previous distinct Dive must be exactly one day/number earlier; the first record needs no predecessor. Gaps fail visibly and need investigation, never fabricated backfill.
  HTTP must be 200 with application/json. Seven unique IDs p1–p7 and nonempty texts are required. Expired data is discarded and retried once. Timeouts and 5xx retry once after 60 seconds (two attempts total). 403/1010 stops immediately with a normal-network-required message; no header impersonation, browser or proxy workaround. Validation failure writes no archive data and exits 1; diagnostic logs and issues remain available.
- `ops.py weekly`: page count, status distribution, additions/removals against a seven-day baseline. Initial reports explicitly mark partial coverage.

Schedules: archive 05:20 UTC; website health + IndexNow 01:00 UTC; weekly Monday 01:30 UTC. GitHub schedules can be delayed. Inactive public-repository schedules may be disabled by GitHub after 60 days. All jobs use one repository concurrency lock, retain HTTP status and first 200 response characters, upload logs even on failure, commit operational state, and open/update issues on errors. No added secret is needed for health/archive; Actions uses its repository-scoped GITHUB_TOKEN to persist files and issues.

IndexNow public verification key and existing root keyLocation belong in `config.json`; the Bing Webmaster account API key is a different credential and must never go here. Scripts never publish or edit the website key file.

Run locally with Python 3.9+ and authenticated `gh`, e.g. `python3 ops.py health`. Scheduled jobs use Python 3.12. Own-site reads use native curl with its default headers; no UA impersonation. Archive transport always uses ordinary urllib directly and stops when blocked.
