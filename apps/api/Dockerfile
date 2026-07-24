# Planarus API — FastAPI + SQLite. Alembic migrates to head on startup.
FROM python:3.11-slim

# gosu lets the entrypoint drop from root to `planarus` after it has fixed the
# bind-mounted /data ownership (#115: the API must run unprivileged).
RUN apt-get update \
 && apt-get install -y --no-install-recommends gosu \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 10001 planarus \
 && useradd --uid 10001 --gid planarus --no-create-home planarus

WORKDIR /app
COPY . /app

# Runtime deps only (no [dev] extras). argon2-cffi / uvloop / httptools ship
# manylinux wheels, so no compiler is needed on slim. If a future dep has no
# wheel, add: RUN apt-get update && apt-get install -y --no-install-recommends gcc
RUN pip install --no-cache-dir . \
 && chmod +x /app/docker-entrypoint.sh \
 && chown -R planarus:planarus /app

EXPOSE 8000

# The entrypoint fixes /data ownership as root, then runs the migration and the
# server as the unprivileged `planarus` user (#115). The app default
# (sqlite:///./planarus.db, cwd=/app) and Alembic both resolve to /app/planarus.db,
# which the entrypoint symlinks onto the persisted /data volume.
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
