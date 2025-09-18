#!/bin/bash
set -euo pipefail

echo "🚀 Bootstrap script for Spotify Clone project"

# Check prerequisites
echo "📋 Checking prerequisites..."
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required"; exit 1; }
command -v terraform >/dev/null 2>&1 || { echo "❌ Terraform is required"; exit 1; }
command -v git >/dev/null 2>&1 || { echo "❌ Git is required"; exit 1; }

# Install pre-commit
echo "🔧 Installing pre-commit..."
pip install pre-commit

# Install pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Initialize git if not already done
if [ ! -d .git ]; then
    echo "🔧 Initializing git repository..."
    git init
    git add .
    git commit -m "chore: initial project scaffold

🚀 Generated with Claude Code

Co-Authored-By: Claude <noreply@anthropic.com>"
fi

# Terraform init (with backend TODO reminder)
echo "🏗️  Initializing Terraform..."
cd infra/terraform/aws/envs/dev
echo "⚠️  TODO: Configure remote backend in providers.tf before running terraform init"
echo "   - Create S3 bucket: spotify-clone-terraform-state-dev"
echo "   - Create DynamoDB table: spotify-clone-terraform-locks"
echo "   - Uncomment backend configuration in providers.tf"
echo ""
echo "   For now, using local backend..."
terraform init || echo "⚠️  Terraform init failed - configure backend first"

cd - > /dev/null

echo "✅ Bootstrap complete!"
echo ""
echo "Next steps:"
echo "1. Configure AWS credentials: aws configure"
echo "2. Set up Terraform remote backend (see TODO in providers.tf)"
echo "3. Start API development: cd apps/api_fastapi && pip install -r requirements.txt"
echo "4. Review PROJECT_RULES.md for development guidelines"