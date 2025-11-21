# Flutter Spotify Clone

Full-stack Spotify clone with Flutter frontend, FastAPI backend, and AWS infrastructure.

## Architecture

- **Frontend:** Flutter (MVVM/Riverpod)
- **Backend:** FastAPI (Python 3.12+)
- **Database:** PostgreSQL (RDS)
- **Cache:** Redis
- **Storage:** S3 + CloudFront
- **Infrastructure:** Terraform (AWS)
- **Observability:** Datadog + Prometheus

## Quick Start

### Prerequisites
- Python 3.12+
- Flutter SDK
- Terraform 1.6+
- Docker
- AWS CLI

### Development Setup

1. **Bootstrap tooling:**
   ```bash
   ./scripts/first10.sh
   ```

2. **Backend (FastAPI):**
   ```bash
   cd apps/api_fastapi
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```

3. **Frontend (Flutter):**
   ```bash
   cd apps/flutter_app
   flutter pub get
   flutter run
   ```

4. **Infrastructure:**
   ```bash
   cd infra/terraform/aws/envs/dev
   # TODO: Configure remote backend first
   terraform init
   terraform plan
   ```

## Testing

- **API Tests:** `pytest apps/api_fastapi/tests/`
- **Widget Tests:** `flutter test`
- **Security:** OWASP ZAP, Nuclei
- **Infrastructure:** Terratest, Kitchen-Terraform

## Operations

- **Runbooks:** `ops/runbooks/`
- **ADRs:** `ops/adr/`
- **Incident Response:** `ops/incident_scenarios/`

## Contributing

1. Follow [PROJECT_RULES.md](./PROJECT_RULES.md)
2. Use conventional commits
3. All PRs require tests + docs
4. Pre-commit hooks must pass

## Security

See [SECURITY.md](./SECURITY.md) for security policies.
