# Pharma71 collection infrastructure v3 (staging)
Separate SEC metadata collection from newsroom collection. SEC observations do not confer newsroom coverage or original-release credit. Strict QA remains unchanged; existing production is untouched.

Configure SEC_USER_AGENT in repository Actions secrets with application/organization name and valid contact email. Missing configuration is recorded as NOT_CONFIGURED. SEC 8-K/6-K metadata is supplementary; original exhibit verification, historical pagination, non-US exchange collection remain pending.

External deployment: build Dockerfile.pharma71 from this branch; mount writable persistent storage at /data/pharma71 (UID 10001), one replica, set SEC_USER_AGENT in secret manager. PHARMA71_RUN_ONCE=1 performs one test; otherwise interval defaults to 1200 seconds. No inbound network listener, no repository writes or email. External worker deployment, artifact transfer and Docker build have not been verified. Audit ledger, state and verified originals remain in persistent storage. GitHub trial stores SQLite in the run artifact, not a rolling Git repository database.

Release gate: compare actual external and GitHub coverage, verify evidence transfer, successor-company scope, sustained 20-minute execution, email dry-run, deduplication and rollback. Do not bypass publisher access controls or claim full coverage from filings alone.

Railway staging: the mount can be owned by root at runtime. Bootstrap changes ownership of only /data/pharma71, drops privileges permanently to UID 10001, then starts the worker. The run emits a compact comparison receipt only after verifying the SQLite record matches the current audit; full raw evidence remains on the mounted volume. This is not yet cross-environment evidence transfer.

Issuer-authored GlobeNewswire organization archives added for BIIB, DNLI, ERAS, KURA, CGEM and GPCR. Archive rows require explicit matching source and publication date; originals require independently matching issuer attribution in header/metadata, title and date. This is supplemental distribution coverage, not full newsroom coverage. Actual response schemas and coverage remain subject to live staging verification. SEC contact must be user-approved; no personal email is sent automatically.

SEC HTML/text exhibits: accession-scoped SEC filing index, EX-99 type validation, raw response hashes, separate ledger table and company-level report/log metrics. Filing date is not press release date; PDF exhibits, historical filings pagination and cross-source semantic deduplication are not yet implemented. SEC originals do not confer newsroom coverage.

SEC identity: explicit US/ADR symbol allowlist and SEC legal issuer-name check; historical ticker-only metrics may include unrelated issuers and are not comparable. TDnet public daily index observations added for 4568,4151,4536,4506; candidate metadata only, no PDF verification or full pagination claim. HKEX automated collection remains pending.
