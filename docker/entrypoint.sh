#!/bin/sh
set -eu

echo "Waiting for PostgreSQL at ${DB_HOST:-db}:${DB_PORT:-5432}..."

python -c "
import os
import socket
import time
import sys

host = os.getenv('DB_HOST', 'db')
port = int(os.getenv('DB_PORT', '5432'))
deadline = time.time() + 90

while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print('PostgreSQL is reachable.')
            sys.exit(0)
    except OSError:
        time.sleep(2)

print(f'Timed out waiting for PostgreSQL at {host}:{port}', file=sys.stderr)
sys.exit(1)
"

echo "Running Alembic migrations..."
alembic upgrade head

echo "Starting application..."
exec "$@"
