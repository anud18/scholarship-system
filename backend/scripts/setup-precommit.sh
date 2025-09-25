#!/bin/bash
# Setup pre-commit hooks for automatic code formatting and linting

set -e

echo "🔧 Setting up pre-commit hooks..."

# Check if we're in the backend directory
if [[ ! -f ".pre-commit-config.yaml" ]]; then
    echo "❌ Error: .pre-commit-config.yaml not found. Run this script from the backend directory."
    exit 1
fi

# Install pre-commit if not already installed
if ! command -v pre-commit &> /dev/null; then
    echo "📦 Installing pre-commit..."
    pip install pre-commit
fi

# Install the pre-commit hooks
echo "🪝 Installing pre-commit hooks..."
pre-commit install

# Run pre-commit on all files to ensure everything is formatted
echo "🎨 Running pre-commit on all files..."
pre-commit run --all-files || {
    echo "⚠️  Some files need formatting. Running black and isort..."
    black .
    isort .
    echo "✅ Files formatted. Please review and commit the changes."
}

echo "🎉 Pre-commit hooks setup complete!"
echo ""
echo "Now every time you commit, the following will run automatically:"
echo "  ✓ Code formatting with black"
echo "  ✓ Import sorting with isort"
echo "  ✓ Linting with flake8"
echo "  ✓ Type checking with mypy"
echo "  ✓ Basic file checks (trailing whitespace, etc.)"
echo ""
echo "To run manually: pre-commit run --all-files"
echo "To skip hooks (not recommended): git commit --no-verify"