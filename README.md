# ProductsChat

Python 3.12 Service Bus worker on AKS. Embeds a question, retrieves filtered pgvector chunks, generates a cited answer, caches the reply, then publishes/acknowledges. The workshop deploys one worker replica: one request at a time, prefetch zero, bounded lock renewal.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest tests -q
docker build --platform linux/amd64 -t products-chat:w1 .
```

Runtime needs `APP_CONFIG_ENDPOINT` / `APP_CONFIG_LABEL`, workload identity and the workshop's Azure dependencies. Settings/secrets load at startup. `/health` listens on 8080.

`rag_core/` is vendored runtime source, also included in ProductsEmbedder. Keep both copies consistent. All dependencies are local to this repository. `inspect_db.py` is included in the image for the workshop's VNet inspection Job.

Messages are at-least-once. Cached results prevent duplicate displayed answers; a crash before caching can repeat a paid model call. Unsupported questions return insufficient information. Unit model tests use deterministic fixtures.

Provisioning, sample questions and real PostgreSQL integration tests: https://github.com/tuba-labs/ai200/tree/main/workshop
