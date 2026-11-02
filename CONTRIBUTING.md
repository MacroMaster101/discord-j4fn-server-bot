# Contributing

Thanks for helping out! Bug reports, ideas and pull requests are all welcome.

## Branches

```
feature/*  →  dev  →  main
```

- **`main`** is what runs in production. Every merge into it deploys automatically. It only accepts pull requests from `dev`.
- **`dev`** is where work comes together. Open your pull request against `dev`. Pushing straight to `dev` is allowed for day-to-day work.
- **`feature/<short-name>`**: create one from `dev` for each change.

[`.github/workflows/branch-flow.yml`](.github/workflows/branch-flow.yml) enforces this on every pull request, so a `feature/*` branch aimed at `main` fails rather than being merged by mistake.

## Local setup

```bash
git clone https://github.com/MacroMaster101/discord-j4fn-server-bot.git
cd discord-j4fn-server-bot
python -m venv .venv
pip install -r requirements.txt
cp .env.example .env   # then fill in your own values
python bot.py
```

The dashboard runs at http://localhost:8080. `DISCORD_TOKEN` is the only value
you must supply to start; the admin password is generated into `.env` on first
run if you leave it empty. Sign in at `/login`. Cloudflare Access sign-in only
works on the deployed site, so leave `CF_ACCESS_*` empty locally.

## Before opening a pull request

Run the same checks CI runs:

```bash
python -m compileall -q bot.py automod.py auth.py test_automod.py test_auth.py
python test_automod.py    # auto-mod detection
python test_auth.py       # authorization boundaries
python -c "import bot"    # imports cleanly
pip-audit -r requirements.txt --strict
```

`test_auth.py` needs `COOKIE_SECURE=0`, since the test client speaks plain
HTTP. Both suites write under `data/` and must clean up after themselves — CI
fails the build if they leave files behind, so check `git status` is clean when
they finish.

- Keep pull requests focused on one change.
- Describe what changed and how you tested it.
- If you touch an authorization path, add a check to `test_auth.py`. A boundary
  nothing asserts is a boundary that quietly stops working.
- Never include tokens, API keys, passwords or files from `data/`.

## Reporting bugs

Open an issue with the **Bug report** template. For anything security related,
follow [SECURITY.md](SECURITY.md) and report it privately instead of opening a
public issue.
