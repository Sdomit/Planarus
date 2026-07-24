#!/bin/sh
# Entrypoint for the Planarus API container (#115: run the app as non-root).
#
# /data is a bind mount, so its host ownership is unpredictable and can't be
# fixed at build time. Fix it here as root, then drop to the unprivileged
# `planarus` user for migrations and the server — so the app can only ever
# write inside its mounted data path, never elsewhere on the host/container.
set -e

mkdir -p /data
chown planarus:planarus /data
# The app and Alembic both resolve ./planarus.db under /app; point it at the
# persisted copy on /data (SQLite keeps -wal/-shm next to the real file).
ln -sf /data/planarus.db /app/planarus.db

gosu planarus alembic upgrade head
exec gosu planarus "$@"
