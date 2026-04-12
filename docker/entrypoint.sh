#!/bin/sh
set -eu

python -c "
import os
import socket
import time
import sys
from urllib.parse import urlparse

database_url = os.getenv('DATABASE_URL')
if database_url:
    parsed = urlparse(database_url)
    host = parsed.hostname
    port = parsed.port or 5432
else:
    host = os.getenv('DB_HOST')
    port = int(os.getenv('DB_PORT', '5432'))

if not host:
    print('Database host is not configured. Set DATABASE_URL or DB_HOST.', file=sys.stderr)
    sys.exit(1)

print(f'Waiting for PostgreSQL at {host}:{port}...')
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
