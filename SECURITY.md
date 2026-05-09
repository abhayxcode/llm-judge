# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities **privately** by emailing `abhayxcode@gmail.com` with `[security]` in the subject line.

Do not open public GitHub issues for security reports.

We aim to acknowledge reports within 2 business days, and to provide a remediation plan within 14 days.

## Disclosure Window

We follow a 90-day standard disclosure window from the date of acknowledgment. We may shorten or extend by mutual agreement with the reporter.

## Scope

In scope:

- Server services (`services/ingest`, `services/api`, `services/workers`)
- SDKs (`packages/sdk-python`, `packages/sdk-ts`)
- Web app (`apps/web`)
- Helm chart and docker-compose deployment configs

Out of scope:

- Third-party dependencies — please report upstream.
- Self-host installations — we'll help where we can but cannot remediate user-managed deployments directly.
