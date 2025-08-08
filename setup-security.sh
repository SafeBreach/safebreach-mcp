#!/bin/bash
# Setup security tools and pre-commit hooks

set -e

echo "🔒 Setting up SafeBreach MCP Security Tools..."

# Install pre-commit
if ! command -v pre-commit &> /dev/null; then
    echo "Installing pre-commit..."
    pip install pre-commit
fi

# Install gitleaks
if ! command -v gitleaks &> /dev/null; then
    echo "Installing gitleaks..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install gitleaks
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        wget https://github.com/gitleaks/gitleaks/releases/latest/download/gitleaks-linux-amd64.tar.gz
        tar -xzf gitleaks-linux-amd64.tar.gz
        sudo mv gitleaks /usr/local/bin/
        rm gitleaks-linux-amd64.tar.gz
    fi
fi

# Install detect-secrets
pip install detect-secrets

# Setup pre-commit hooks
echo "Installing pre-commit hooks..."
pre-commit install

# Initialize secrets baseline
echo "Creating secrets baseline..."
detect-secrets scan --all-files --baseline .secrets.baseline

# Test the hooks
echo "Testing pre-commit hooks..."
pre-commit run --all-files

# Setup environment template
if [ ! -f .env ]; then
    echo "Creating .env from template..."
    cp .env.template .env
    echo "⚠️  Please edit .env file with your actual tokens"
fi

# Scan existing repository for secrets
echo "Scanning repository for existing secrets..."
gitleaks detect --config .gitleaks.toml --verbose

# Make Claude launcher executable
chmod +x claude-launcher.sh

echo "✅ Security setup complete!"
echo ""
echo "🤖 CLAUDE INTEGRATION READY!"
echo "From now on, ALWAYS launch Claude using:"
echo "   ./claude-launcher.sh"
echo ""
echo "This ensures Claude has:"
echo "✅ Full project knowledge and best practices"
echo "✅ Security context and token handling awareness"
echo "✅ Current git status and environment info"
echo "✅ Pre-validated secure environment"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your actual tokens (template created)"
echo "2. Never commit the .env file or any real secrets"
echo "3. Use placeholders in documentation (your-token-here)"
echo "4. Always launch Claude with: ./claude-launcher.sh"
echo "5. Run 'pre-commit run --all-files' before commits"
echo "6. Review SECURITY_GUIDELINES.md for full security practices"
echo ""
echo "🚀 Ready to launch Claude securely:"
echo "   ./claude-launcher.sh"