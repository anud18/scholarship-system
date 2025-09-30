#!/bin/bash
# Quick script to format all Python code

set -e

echo "🎨 Formatting Python code..."

# Change to backend directory if not already there
if [[ -f "app/main.py" ]]; then
    echo "✓ Already in backend directory"
else
    echo "🔄 Changing to backend directory..."
    cd "$(dirname "$0")/.."
fi

# Run black formatter
echo "🖤 Running black..."
black . --line-length=120

# Run isort for import sorting
echo "📚 Running isort..."
isort . --profile black --line-length=120

# Run flake8 for linting (informational)
echo "🔍 Running flake8..."
flake8 . --max-line-length=120 --extend-ignore=E203,W503,E501 || {
    echo "⚠️  Flake8 found some issues, but formatting is complete."
}

echo "✅ Code formatting complete!"
echo ""
echo "Files have been formatted and imports sorted."
echo "Please review the changes before committing."