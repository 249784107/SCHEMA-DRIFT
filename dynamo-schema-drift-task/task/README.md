# Schema Drift Sanitizer & Eventual Consistency Resolver

**Category:** Data Querying and Databases
**Sub-category:** NoSQL and Document Stores

## Repo layout

```
Dockerfile                  builds the task container (Ubuntu + MongoDB 7.0)
entrypoint.sh                boots mongod, loads seed data, hands off to agent/verifier
task.yaml                    DRAFT Harbor manifest — see warning below
INSTRUCTIONS.md              agent-facing task brief, copied to /app at build time
app/
  target_schema.json         unified schema every migrated doc must satisfy
  CONFLICT_RESOLUTION_RULES.md  disclosed precedence rules (agent-visible)
  data_seed.jsonl            raw pre-migration collection dump (also loaded into mongod)
solution/                    NOT copied into /app — grading material only
  ground_truth.json          expected resolution for each seeded trap order
  pre_migration_snapshot.json  control fields for the non-destructiveness check
solution_reference/          NOT copied into /app — proves the task is solvable
  normalize.py                phase 1: structural fingerprinting per doc
  resolve.py                  phase 2: the 4-rule conflict resolution logic
  migrate_core.py             pure orchestration (no pymongo, unit-testable)
  migrate.py                  thin pymongo wrapper for the live container
  migrate.sh                  shell entrypoint the verifier re-invokes for idempotency
scripts/
  generate_seed_data.py       regenerates app/data_seed.jsonl + solution/*.json
verifier/
  verify.py                   entrypoint: fetches live Mongo state, runs checks, exits 0/1
  verify_core.py               pure verification logic (pymongo-free, unit-testable)
tests/
  test_verify_core.py          proves the verifier passes a correct migration and
                                catches every seeded failure mode (7 cases)
  test_reference_solution_e2e.py  runs the actual reference solution against real
                                seed data, scores it with the real verifier logic,
                                and checks idempotency (2 cases) — the strongest
                                proof available that the task is solvable
  _fake_jsonschema.py          minimal jsonschema shim for offline testing only —
                                NOT used in the real image (Dockerfile installs the
                                real `jsonschema` package)
```

## What was validated in this environment (no network / no Docker / no Mongo available here)

- `scripts/generate_seed_data.py` runs cleanly and produces:
  - 2000 baseline single-generation orders across all 10 generations
  - 5 explicitly seeded trap orders, one per branch of the disclosed
    precedence rules (terminal-status protection, logical-clock override,
    schema-only generation precedence, fallback highest-generation-wins,
    and a combined terminal+schema-only case)
  - `ground_truth.json` and `pre_migration_snapshot.json` for grading
- All emitted JSON (`data_seed.jsonl`, `target_schema.json`, ground truth,
  snapshot) parses correctly.
- `verifier/verify_core.py` — the pure grading logic — was unit tested
  against 7 cases: a fully correct migration (must pass all 4 non-Mongo
  checks) and one deliberately broken migration per failure mode. **All 7 pass.**
- **A full reference solution was written (`solution_reference/`) and run
  end-to-end against the real seed data.** It passes all 4 core checks
  (schema validity, trap correctness, data integrity, non-destructiveness)
  and is idempotent across 3 repeated runs. This is the strongest evidence
  available that the task is solvable as specified without a live Mongo
  instance. Along the way this caught and fixed two real bugs:
  1. The seed generator gave each competing update document for a trap
     order a random `customer_id` instead of a consistent one, which broke
     the non-destructiveness check's control-field invariant (fixed in
     `generate_seed_data.py`).
  2. The normalizer recomputed an already-unified document's generation
     rank structurally instead of reading back its stored
     `schema_generation`, which silently changed the rank on every
     re-run and broke idempotency (fixed in `normalize.py`).
- `task.yaml` is well-formed YAML.

## What still needs to happen in your environment before opening the PR

This sandbox has no network access and no Docker/MongoDB installed, so the
following could **not** be verified here and need to happen after you
clone the real repo:

1. **Reconcile `task.yaml` against the real Harbor manifest schema.** I
   drafted it from the pattern described in the brief, not from the actual
   spec at the workflow link (which I can't fetch). Compare it against an
   existing reference task already in the Dynamo repo and rename/restructure
   fields to match exactly.
2. **`docker build` the image** and confirm MongoDB 7.0 installs cleanly
   on whatever base the real Harbor images expect (I used `ubuntu:24.04`
   as a placeholder — the real repo may mandate a specific base image).
3. **Run `solution_reference/migrate.sh` against a live mongod in the
   built container**, then run `verifier/verify.py` against it and confirm
   exit code 0. Only the pymongo-free core logic (`migrate_core.py` +
   `verify_core.py`) was tested here — the actual `pymongo` I/O in
   `migrate.py`/`verify.py` (connection handling, `find()`, delete/insert
   semantics under concurrent writes) is untested in this sandbox and is
   the main remaining risk.
4. Run whatever `harbor validate` / CI command the workflow doc specifies
   before submitting the PR.
5. Decide whether to ship `solution_reference/` in the PR (useful for
   reviewers to confirm solvability) or keep it out of the final agent
   image entirely (it currently isn't copied into the Docker image at all
   — only referenced by the Dockerfile comment — so it's safe either way,
   but check the Dynamo repo's convention for where reference solutions live).

## Regenerating seed data

```
python3 scripts/generate_seed_data.py
```

Deterministic (seeded with `random.seed(1438858)`), safe to re-run.

## Running verifier self-tests

```
cd tests
python3 -c "
import sys; sys.path.insert(0, '.')
import _fake_jsonschema as jsonschema
sys.modules['jsonschema'] = jsonschema
exec(open('test_verify_core.py').read())
"
```

(In the real image, just `pip install jsonschema` and run
`python3 test_verify_core.py` directly — the shim is only a workaround for
this offline sandbox.)
