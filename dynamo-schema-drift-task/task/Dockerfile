FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# --- MongoDB 7.0 + Python + tooling ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg python3 python3-pip python3-venv jq \
    && curl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] http://repo.mongodb.org/apt/ubuntu noble/mongodb-org/7.0 multiverse" \
       > /etc/apt/sources.list.d/mongodb-org-7.0.list \
    && apt-get update && apt-get install -y mongodb-org \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --break-system-packages --no-cache-dir pymongo jsonschema

RUN mkdir -p /data/db /app /solution /verifier

# --- Agent-visible task files ---
COPY app/target_schema.json /app/target_schema.json
COPY app/CONFLICT_RESOLUTION_RULES.md /app/CONFLICT_RESOLUTION_RULES.md
COPY app/data_seed.jsonl /app/data_seed.jsonl
COPY INSTRUCTIONS.md /app/INSTRUCTIONS.md

# --- Hidden solution/grading material (NOT under /app) ---
COPY solution/ground_truth.json /solution/ground_truth.json
COPY solution/pre_migration_snapshot.json /solution/pre_migration_snapshot.json

# --- Verifier ---
COPY verifier/verify.py /verifier/verify.py
COPY verifier/verify_core.py /verifier/verify_core.py

# --- Entrypoint: start mongod, load seed data into orders_db.orders ---
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /app
ENTRYPOINT ["/entrypoint.sh"]
