# Security Policy

Daily Scholar is a personal research project maintained by a single author on a
best-effort basis. Security reports are taken seriously and will be acknowledged
promptly.

## Supported versions

Only the `main` branch receives security fixes. Forks and older tags are not
patched.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security problems.

Instead, report privately via one of:

- GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
  on this repository (preferred), or
- Email: **gcomalley4@gmail.com** with subject line `[daily-scholar security]`.

Please include:

- A description of the issue and its impact
- Steps to reproduce, or a proof-of-concept
- The affected commit SHA or branch
- Your preferred contact for follow-up

## What to expect

- Acknowledgement within 5 business days
- A triage decision (accepted / not-a-vuln / out-of-scope) within 14 days
- Coordinated disclosure once a fix is shipped — credit given by default unless
  you ask to remain anonymous

## In scope

- Authentication / authorization bypasses around the Cloudflare Access layer
- User-scoped data leaks across the 9 user-scoped tables
  (`seen_papers`, `archived_papers`, `archived_quizzes`, `archived_topic_reviews`,
  `paper_pdfs`, `daily_content_cache`, `user_stats`, `push_subscriptions`,
  `user_settings`)
- Server-side request forgery, injection, or RCE in the FastAPI backend
- Pre-signed URL or storage-key abuse against the B2 storage adapter
- VAPID / Web Push key handling

## Out of scope

- Findings against dependencies that are already disclosed upstream (please
  report those to the upstream maintainer)
- Issues that require an already-compromised Cloudflare Access identity
- Rate-limiting and denial-of-service against a single-user beta instance
- Self-hosted misconfigurations (missing env vars, exposed `__local__` user, etc.)
- Reports generated solely by automated scanners with no demonstrated impact

## Safe harbor

Good-faith security research that follows this policy will not be pursued
legally. Please avoid: accessing other users' data beyond what's needed to
demonstrate the issue, degrading service availability, or publishing the
finding before a fix is released.
