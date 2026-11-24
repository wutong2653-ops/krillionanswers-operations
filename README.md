# Krillion Answers operations

Public operational scripts and question metadata only. No website source, deployments, DNS credentials, answers, or official guides.

- `ops.py health`: read all sitemap URLs, HTTP status, title, canonical and noindex; alert through GitHub Issues.
- `ops.py indexnow`: diff URL/lastmod against the last accepted snapshot; submit only new/changed URLs. Verify the existing on-host key file first. HTTP 429 retains the queue; Actions retries once after 45 minutes. A second 429 stays pending and opens an informational issue, never counts as accepted.
- `ops.py archive`: one plain Python GET to the official today endpoint; save only question IDs/prompts and metadata to `latest.json` and immutable `history/YYYY-MM-DD.json`. Any block stops the attempt, without browser, UA spoofing, proxy changes, or retries. No guides are accessed.
- `ops.py weekly`: page count, status distribution, additions/removals against a seven-day baseline. Initial reports explicitly mark partial coverage.

Schedules: archive 00:10 UTC; website health + IndexNow 01:00 UTC; weekly Monday 01:30 UTC. GitHub schedules can be delayed. Inactive public-repository schedules may be disabled by GitHub after 60 days. All jobs use one repository concurrency lock, retain HTTP status and first 200 response characters, upload logs even on failure, commit operational state, and open/update issues on errors. No added secret is needed for health/archive; Actions uses its repository-scoped GITHUB_TOKEN to persist files and issues.

IndexNow public verification key and existing root keyLocation belong in `config.json`; the Bing Webmaster account API key is a different credential and must never go here. Scripts never publish or edit the website key file.

Run locally with Python 3.9+ and authenticated `gh`, e.g. `python3 ops.py health`. Scheduled jobs use Python 3.12. `curl` is available on GitHub runners if the own-site health transport is configured to use it. Archive transport always uses ordinary urllib directly and stops when blocked.
