# Pharma71 collection infrastructure v3 (staging)
Separate SEC metadata collection from newsroom collection. SEC observations do not confer newsroom coverage or original-release credit. Strict QA remains unchanged; existing production is untouched.

Configure SEC_USER_AGENT in repository Actions secrets with application/organization name and valid contact email. Missing configuration is recorded as NOT_CONFIGURED. SEC 8-K/6-K metadata is supplementary; original exhibit verification, historical pagination, non-US exchange collection remain pending.

External deployment: build Dockerfile.pharma71 from this branch; mount writable persistent storage at /data/pharma71 (UID 10001), one replica, set SEC_USER_AGENT in secret manager. PHARMA71_RUN_ONCE=1 performs one test; otherwise interval defaults to 1200 seconds. No inbound network listener, no repository writes or email. External worker deployment, artifact transfer and Docker build have not been verified. Audit ledger, state and verified originals remain in persistent storage. GitHub trial stores SQLite in the run artifact, not a rolling Git repository database.

Release gate: compare actual external and GitHub coverage, verify evidence transfer, successor-company scope, sustained 20-minute execution, email dry-run, deduplication and rollback. Do not bypass publisher access controls or claim full coverage from filings alone.
