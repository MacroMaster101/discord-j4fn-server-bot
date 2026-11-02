# Pinned by digest, not by the floating 3.12-slim tag, so a build is
# reproducible and a base-image bump is a deliberate commit. The deploy runs
# `docker compose build --pull`, so this digest is what actually gets fetched.
# Currently Python 3.12.16.
FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a normal user: the app decodes untrusted Discord attachments through
# Pillow, and as root any break out of that would own the bind-mounted .env and
# data/ on the host rather than just read them.
#
# uid 1001 is not arbitrary -- it matches the `ubuntu` account that owns .env
# (mode 600) and data/ on the server, which are bind-mounted in. A different uid
# here cannot write them, and the bot rewrites .env at runtime.
RUN useradd --uid 1001 --user-group --no-create-home --shell /usr/sbin/nologin app \
 && chown -R app:app /app
USER app

# /health is unauthenticated and cheap, so `docker compose ps` can say whether
# the dashboard is actually answering rather than only whether the process is up.
HEALTHCHECK --interval=60s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request,os,sys;\
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','8080'), timeout=4).status==200 else 1)"]

# Runs the bot, which also starts the dashboard on its own thread (waitress).
CMD ["python", "bot.py"]
