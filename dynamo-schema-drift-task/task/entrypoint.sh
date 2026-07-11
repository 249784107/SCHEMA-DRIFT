#!/bin/bash
set -euo pipefail

mongod --fork --logpath /var/log/mongod.log --dbpath /data/db --bind_ip 127.0.0.1

# wait for mongod
for i in $(seq 1 30); do
  if mongosh --quiet --eval "db.runCommand({ping:1})" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# load seed data into orders_db.orders (idempotent: only load if empty)
COUNT=$(mongosh --quiet orders_db --eval "db.orders.countDocuments({})")
if [ "$COUNT" -eq 0 ]; then
  mongoimport --db orders_db --collection orders --file /app/data_seed.jsonl
fi

# hand off to whatever the container was started with (agent shell, or the
# verifier, depending on harness invocation)
exec "$@"
