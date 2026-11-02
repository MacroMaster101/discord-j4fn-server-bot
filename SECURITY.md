# Security Policy

## Supported versions

This project is deployed continuously from `main`. Only the currently deployed
commit on `main` is supported — there are no release branches and no backports.
If you are running a fork, update to the latest `main` before reporting.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Report it through GitHub's private vulnerability reporting:
[**Report a vulnerability**](https://github.com/MacroMaster101/discord-j4fn-server-bot/security/advisories/new).
That opens a private advisory visible only to the maintainers.

Please include:

- what an attacker can do, not only what looks wrong
- the affected route, command or file
- the steps to reproduce it, and whether you needed to be signed in
- anything you already tried that did *not* work, which often narrows the cause

You can expect an acknowledgement within a few days. This is a hobby project
maintained by one person, so there is no paid bounty and no guaranteed fix
window — but genuine reports are read and acted on, and you will be credited in
the advisory unless you ask otherwise.

## What is in scope

The bot and its web console, specifically:

- authorization on `/admin*` — anything reachable without a valid Cloudflare
  Access identity or the admin password
- the Discord OAuth sign-in flow (state handling, redirect validation, acting on
  a guild you do not administer)
- session and cookie handling
- injection of any kind, path traversal under `data/`, or SSRF
- the auto-moderation pipeline accepting input that crashes or hangs the bot

## What is out of scope

- Missing hardening with no exploit path (headers, a version banner, a
  theoretical weakness nothing reaches)
- Denial of service through sheer volume against the Cloudflare edge
- Vulnerabilities in Discord, Cloudflare or other third-party services —
  report those to the service concerned
- Social engineering of server members, and anything requiring access to the
  host or to a maintainer's account
- Automated scanner output pasted without a demonstrated impact

## Operational notes for anyone self-hosting

- The web origin is not meant to face the internet. Set
  `DASHBOARD_BIND_ADDRESS=127.0.0.1` and publish only through the tunnel.
- `/admin` must be covered by a Cloudflare Access application, and any admin API
  must live under `/admin/api/...`. Cloudflare injects identity headers only on
  paths inside the Access app, so a bare `/api/...` route bypasses it entirely.
- Never commit `.env`. It holds the bot token, the tunnel token, the OAuth client
  secret and the Flask secret key; a single leak means rotating all of them.
