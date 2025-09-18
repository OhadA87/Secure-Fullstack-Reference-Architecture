# PROJECT_RULES.md

## 0) Operating Principles (applies to ALL changes)

**No guessing.** If requirements or inputs are ambiguous, STOP and return a short list of clarifying questions.

**Ground in repo.** Always cite the exact files and line ranges you're changing. Prefer diff-style patches.

**Conform to existing patterns.** Match current architecture, naming, and dependency choices unless an ADR says otherwise.

**Security-first.** Never add secrets/tokens to code or logs. Prefer OIDC/SSO or env+secret managers (AWS SSM/GCP SM).

**Small PRs only.** Keep changes <300 LOC, with tests and docs. Decompose work if larger.

**If unknown, write TODOs.** Don't invent APIs, data models, or endpoints. Use # TODO(owner): … with assumptions.

## 1) Source of Truth & Docs

**Architecture:** Flutter (MVVM/Riverpod) → FastAPI → Postgres (RDS/Cloud SQL), Redis, S3/CloudFront (media), WAF/ALB.

**Infra:** Terraform modules (AWS primary), Checkov policies, Terratest, Kitchen-Terraform.

**Observability:** Datadog APM+logs+metrics (+ Prometheus /metrics).

**Docs required per change:**
- Update or create an ADR if architecture or dependencies change.
- Update README sections impacted (quickstart/ops).
- If risk/security relevant, add a note to SECURITY.md and BIA.
- When adding endpoints/schemas, also update: OpenAPI description, validation models, and tests.

## 2) Git & CI hygiene

**Conventional Commits:** feat:, fix:, perf:, refactor:, docs:, test:, chore:.

**PR checklist:** tests passing, pre-commit clean (ruff/black/mypy, terraform fmt/validate/tflint, checkov), no secrets.

**Environments:** dev auto, staging/prod require approvals. Workflows must respect environment gates.

## 3) Backend (FastAPI) rules

### Code style
- Python ≥ 3.12, black + ruff + mypy. Prefer pydantic v2 models; type everything.
- Use Dependency Injection (Depends) for services (db, cache, auth).

### Security
- JWT access + refresh; sessionless by default (or Redis for server-side sessions).
- RBAC helper: require_roles("user","admin"). All admin paths require RBAC + audit logging.
- Validation everywhere: never accept dict/Any from client; define request/response models.
- Rate limiting: SlowAPI decorators at endpoints + Nginx burst limiting.
- CORS locked to known app origins.
- Input/Output size limits; reject oversize payloads.
- Secrets only from env/SSM/Secret Manager; no defaults for prod.

### Performance
- Use async endpoints where I/O bound.
- DB: SQLAlchemy with connection pooling; prefer pgbouncer or RDS Proxy for scaling.
- Cache reads commonly accessed queries in Redis with TTL + cache keys noted in comments.

### Observability
- Add/keep Prometheus /metrics. Custom counters:
  - rbac_denials_total, rate_limit_hits_total, auth_failures_total.
- Datadog tracing via ddtrace-run. Ensure service/env/version tags set.

### Testing
- pytest with httpx.AsyncClient for API tests.
- For each endpoint change: happy path, auth failure, validation error, RBAC denial.

### Never do
- Don't return raw DB objects to clients.
- Don't log PII/secrets. Use structured logs with fields redacted.

## 4) Frontend (Flutter, MVVM/Riverpod)

- **State:** Riverpod for state and DI; prefer immutable models (freezed).
- **Errors:** Central error handler; show safe messages; record technical details to telemetry, not UI.
- **Networking:** Typed API clients; handle 401/403 globally (token refresh); exponential backoff.
- **Testing:** Widget tests for critical screens; golden tests for stable UI; integration test for auth flow.
- **Accessibility & Perf:** 60fps target; avoid unnecessary rebuilds; image caching; skeleton loaders.

## 5) API Contracts & Schema Evolution

- Maintain OpenAPI (FastAPI generates, but keep docstrings precise).
- Backward compatibility: additive changes preferred. Breaking change requires ADR + version bump.
- DB changes: always through migrations (Alembic). Add rollback notes.

## 6) Infrastructure (Terraform) rules

- Modules for VPC, ALB+WAF, ECS service, RDS, Redis, CloudFront+S3. No hard-coding ARNs.
- State: Remote S3 + DynamoDB lock (never local in CI).
- Checkov must pass (no criticals). tflint clean.
- Terratest minimal apply in sandbox or plan with checks; Kitchen-Terraform/Inspec for security controls.
- Tagging: service, env, owner, cost-center.
- Networking: Private subnets for data planes; public only for ALB/CloudFront. No public DB.
- WAF: attach to ALB; managed OWASP + tuned exceptions documented.

## 7) Security testing & posture

- OWASP ZAP: run on staging; don't whitelist without issue+reason.
- Nuclei: keep targets.txt updated; fix high/critical within SLA.
- Scout Suite: run monthly; track posture deltas in ops/compliance/reports/.
- Secret scanning: trufflehog pre-commit and in CI; block PRs with leaks.

## 8) Monitoring, SLOs & Incident response

- **SLOs:** API p95 < 100ms, error rate < 0.5%, availability 99.9%.
- **Dashboards:** latency, RPS, error rate, DB pool saturation, Redis hit ratio, WAF blocks, rate-limit hits.
- **Alerts:** paging for SLO breach and auth spike.
- **Runbooks** in ops/runbooks/; changes must reference runbook steps.
- **PIR** required for any Sev-2+ incident; target MTTR < 60m.

## 9) Dependencies & supply chain

- Pin versions; upgrade via Dependabot weekly.
- New libs require justification (why existing tools don't suffice) + ADR entry.
- Container images: slim base images; run as non-root; scan with hadolint.

## 10) Performance & cost budgets

- **Perf budgets:** endpoint adds <5ms server time unless justified. Load test results in ops/scalability_reports/.
- **Cost:** Prefer on-demand for demo; document RDS/ECS sizing rationale and monthly estimates. Add cost notes to ADRs.

## 11) Deliverable shape for AI changes (what to output)

When implementing a change, always output:
1. **Plan** (1–5 bullets): intent, impacted files, trade-offs.
2. **Diff patch** per file (unified diff or fenced code blocks).
3. **Tests** added/updated.
4. **Docs updated** (ADR/README/runbook) or state "no doc changes needed".
5. **Risks & rollback** (1–2 bullets).
6. **Follow-ups/TODOs** if any.

## 12) Hallucination Guards (hard rules)

- If a file doesn't exist, create it explicitly and show contents. Don't claim existing code.
- If a config key or API route isn't found, ask or mark TODO—don't fabricate.
- If a command requires external access (e.g., GitHub envs), just produce the file(s) and a manual step checklist.
- Prefer explicit examples from this repo over generic "best practices" unless requested.

## Language-Specific Snippets (keep handy)

### FastAPI Endpoint Template
```python
@router.post("/auth/login", response_model=AuthTokens)
@limiter.limit("10/second")
async def login(req: LoginRequest):
    # validate input
    # verify bcrypt hash
    # issue JWT + refresh (exp, iat, aud, jti)
    # audit log (without secrets/PII)
    return AuthTokens(access_token=..., refresh_token=...)
```

### Terraform Module Header
```hcl
terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}
# No hard-coded ARNs. Inputs via variables; outputs minimal and non-sensitive.
```

### GitHub Actions Guard (example)
```yaml
permissions:
  contents: read
  id-token: write   # prefer OIDC over static keys
concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

## Prompt Templates (for daily use in Cursor)

### Implement feature
**Goal:** Add /playlists/{id} GET with RBAC(user/admin), Redis cache (60s), and tests.
**Constraints:** No secrets; p95 budget <100ms; update OpenAPI and README.
**Deliverables:** Plan, diffs, tests, docs, risks/rollback.

### Refactor
**Goal:** Extract auth into service with clear interface; keep API identical.
**Constraints:** 0 behavior change; 100% tests green; mypy clean.
**Deliverables:** Plan, diffs, tests unchanged (prove), ADR note if structure changed.

### Infra
**Goal:** Add Redis module to AWS dev env and wire to API via env vars.
**Constraints:** No public access; Checkov & tflint must pass.
**Deliverables:** Terraform diffs, outputs->workflow env, app .env template, tests (terratest or plan assertions), manual apply steps.

### Security hardening
**Goal:** Add SlowAPI + Nginx burst limiting to all auth routes; document limits and runbook for lockouts.
**Deliverables:** Code diffs, config, tests (rate-limit hits), runbook update.