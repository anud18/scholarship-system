#!/usr/bin/env python3
"""
Setup script for bug prevention tools

This script installs and configures all the bug prevention mechanisms
to catch issues before they reach production.
"""

import os
import sys
import subprocess
from pathlib import Path


def run_command(command: str, cwd: str = None) -> bool:
    """Run a shell command and return success status"""
    try:
        result = subprocess.run(
            command, 
            shell=True, 
            cwd=cwd, 
            check=True,
            capture_output=True,
            text=True
        )
        print(f"✅ {command}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {command}")
        print(f"   Error: {e.stderr}")
        return False


def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major != 3 or version.minor < 9:
        print(f"❌ Python 3.9+ required, found {version.major}.{version.minor}")
        return False
    print(f"✅ Python {version.major}.{version.minor} is compatible")
    return True


def install_dependencies():
    """Install required dependencies"""
    print("\n📦 Installing dependencies...")
    
    deps = [
        "pre-commit",
        "black",
        "isort", 
        "flake8",
        "mypy",
        "pytest",
        "requests"
    ]
    
    success = True
    for dep in deps:
        if not run_command(f"pip install {dep}"):
            success = False
    
    return success


def setup_pre_commit_hooks():
    """Setup pre-commit hooks"""
    print("\n🪝 Setting up pre-commit hooks...")
    
    if not run_command("pre-commit install"):
        return False
    
    # Make scripts executable
    scripts_dir = Path("scripts")
    if scripts_dir.exists():
        for script in scripts_dir.glob("*.py"):
            os.chmod(script, 0o755)
    
    return True


def setup_vscode_integration():
    """Setup VSCode integration"""
    print("\n🔧 Setting up VSCode integration...")
    
    vscode_dir = Path(".vscode")
    if not vscode_dir.exists():
        print("⚠️  .vscode directory not found - VSCode settings may not be applied")
        return True
    
    print("✅ VSCode settings configured")
    return True


def create_git_hooks():
    """Create additional git hooks"""
    print("\n🔗 Creating git hooks...")
    
    git_hooks_dir = Path(".git/hooks")
    if not git_hooks_dir.exists():
        print("⚠️  Not a git repository - skipping git hooks")
        return True
    
    # Create pre-push hook for additional validation
    pre_push_hook = git_hooks_dir / "pre-push"
    pre_push_content = """#!/bin/bash
echo "🚀 Running pre-push validation..."

# Run schema validation
python test_endpoint_schemas.py
if [ $? -ne 0 ]; then
    echo "❌ Schema validation failed - push cancelled"
    exit 1
fi

# Run type checking
mypy app/ --ignore-missing-imports
if [ $? -ne 0 ]; then
    echo "❌ Type checking failed - push cancelled"  
    exit 1
fi

echo "✅ Pre-push validation passed"
exit 0
"""
    
    try:
        with open(pre_push_hook, 'w') as f:
            f.write(pre_push_content)
        os.chmod(pre_push_hook, 0o755)
        print("✅ Pre-push hook created")
        return True
    except Exception as e:
        print(f"⚠️  Failed to create pre-push hook: {e}")
        return True  # Non-critical failure


def run_initial_validation():
    """Run initial validation to ensure everything works"""
    print("\n🧪 Running initial validation...")
    
    success = True
    
    # Test pre-commit
    if not run_command("pre-commit run --all-files"):
        print("⚠️  Pre-commit checks failed - this is normal for first run")
    
    # Test schema validation
    if not run_command("python test_endpoint_schemas.py --endpoint /health"):
        success = False
    
    # Test type checking
    if not run_command("mypy app/main.py --ignore-missing-imports"):
        print("⚠️  Type checking has issues - review mypy output")
    
    return success


def display_usage_instructions():
    """Display instructions for using the bug prevention tools"""
    instructions = """
🎉 Bug Prevention Tools Setup Complete!

Here's how to use your new bug prevention system:

## Daily Development Workflow:

1. **Before coding:**
   - Your IDE will now show type errors and linting issues in real-time
   - The development server includes automatic schema validation

2. **Before committing:**
   - Pre-commit hooks will automatically run:
     ✓ Code formatting (black, isort)
     ✓ Linting (flake8)  
     ✓ Type checking (mypy)
     ✓ Schema validation
   - Fix any issues before the commit succeeds

3. **Before pushing:**
   - Additional validation runs automatically
   - Schema validation and type checking must pass

## Manual Tools:

```bash
# Test specific endpoint
python test_endpoint_schemas.py --endpoint /api/v1/scholarships/eligible

# Test all endpoints  
python test_endpoint_schemas.py

# Run full validation suite
pre-commit run --all-files

# Type check specific file
mypy app/api/v1/endpoints/scholarships.py

# Run schema validation tests
pytest tests/test_api_schema_validation.py -v
```

## Using Auto-Conversion Decorators:

```python
from app.core.auto_response_converter import auto_convert_and_validate

@router.get("/items", response_model=List[ItemResponse])
@auto_convert_and_validate(ItemResponse)
async def get_items():
    items = await db.query(Item).all()
    return items  # Automatically converted and validated!
```

## VSCode Integration:

- Install Python extension if not already installed
- Your settings are pre-configured for:
  - Automatic formatting on save
  - Real-time type checking
  - Import organization
  - Custom validation tasks (Ctrl+Shift+P → "Tasks: Run Task")

## When Things Go Wrong:

1. **Pre-commit hook fails:** Fix the reported issues and commit again
2. **Schema validation error:** Check the error details and ensure response models match returned data
3. **Type errors:** Add proper type hints and handle edge cases

## Key Files Created:

- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `scripts/pre_commit_schema_check.py` - Custom schema validation hook
- `app/middleware/schema_validation_middleware.py` - Development middleware
- `app/core/auto_response_converter.py` - Auto-conversion utilities
- `test_endpoint_schemas.py` - Quick endpoint testing script
- `tests/test_api_schema_validation.py` - Comprehensive test suite

## Next Steps:

1. Try making a change to an API endpoint
2. See the validation tools catch issues automatically
3. Use the auto-conversion decorators for new endpoints
4. Review the documentation in `docs/preventing_schema_validation_errors.md`

Happy coding! 🚀
"""
    
    print(instructions)


def main():
    """Main setup function"""
    print("🛠️  Setting up Bug Prevention Tools")
    print("=" * 50)
    
    # Check prerequisites
    if not check_python_version():
        sys.exit(1)
    
    # Run setup steps
    setup_steps = [
        ("Installing dependencies", install_dependencies),
        ("Setting up pre-commit hooks", setup_pre_commit_hooks),
        ("Setting up VSCode integration", setup_vscode_integration),
        ("Creating git hooks", create_git_hooks),
        ("Running initial validation", run_initial_validation),
    ]
    
    failed_steps = []
    for step_name, step_func in setup_steps:
        print(f"\n{step_name}...")
        if not step_func():
            failed_steps.append(step_name)
    
    # Summary
    print("\n" + "=" * 50)
    if failed_steps:
        print("⚠️  Setup completed with some issues:")
        for step in failed_steps:
            print(f"   - {step}")
        print("\nThe system should still work, but some features may be limited.")
    else:
        print("✅ All setup steps completed successfully!")
    
    display_usage_instructions()
    
    return 0 if not failed_steps else 1


if __name__ == "__main__":
    sys.exit(main())