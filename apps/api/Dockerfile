# AgentBoard API — FastAPI + SQLite. Alembic migrates to head on startup.
FROM python:3.11-slim

WORKDIR /app
COPY . /app

# Runtime deps only (no [dev] extras). argon2-cffi / uvloop / httptools ship
# manylinux wheels, so no compiler is needed on slim. If a future dep has no
# wheel, add: RUN apt-get update && apt-get install -y --no-install-recommends gcc
RUN pip install --no-cache-dir .

EXPOSE 8000

# The app default (sqlite:///./agentboard.db, cwd=/app) and Alembic
# (alembic.ini → sqlite:///agentboard.db, cwd=/app) both resolve to
# /app/agentboard.db. Symlink it onto the /data volume so they share one
# persisted file (SQLite puts -wal/-shm next to the real file, i.e. on /data).
CMD ["sh", "-c", "ln -sf /data/agentboard.db /app/agentboard.db && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
