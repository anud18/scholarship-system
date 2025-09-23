#!/usr/bin/env python3
"""
Pre-commit hook to validate API endpoint schemas

This script runs before each commit to catch schema validation issues
early in the development process.
"""

import ast
import sys
from typing import List, Dict, Set, Optional
from pathlib import Path


class APIEndpointAnalyzer(ast.NodeVisitor):
    """Analyze FastAPI endpoints for potential schema issues"""
    
    def __init__(self):
        self.issues: List[Dict] = []
        self.endpoints: List[Dict] = []
        self.current_file = ""
        self.imports: Set[str] = set()
        self.response_models: Dict[str, str] = {}
    
    def analyze_file(self, file_path: str) -> List[Dict]:
        """Analyze a single Python file for API endpoint issues"""
        self.current_file = file_path
        self.issues = []
        self.endpoints = []
        self.imports = set()
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content)
            self.visit(tree)
            
        except Exception as e:
            self.issues.append({
                'type': 'parse_error',
                'message': f"Failed to parse {file_path}: {e}",
                'severity': 'error',
                'line': 0
            })
        
        return self.issues
    
    def visit_Import(self, node: ast.Import):
        """Track imports"""
        for alias in node.names:
            self.imports.add(alias.name)
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Track from imports"""
        if node.module:
            for alias in node.names:
                self.imports.add(f"{node.module}.{alias.name}")
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node: ast.FunctionDef):
        """Analyze function definitions for FastAPI endpoints"""
        # Check if this is a FastAPI endpoint
        router_decorators = []
        response_model = None
        
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr in ['get', 'post', 'put', 'delete', 'patch']:
                        router_decorators.append(decorator.func.attr)
                        
                        # Extract response_model from decorator
                        for keyword in decorator.keywords:
                            if keyword.arg == 'response_model':
                                response_model = self._extract_response_model(keyword.value)
        
        if router_decorators:
            endpoint_info = {
                'name': node.name,
                'line': node.lineno,
                'methods': router_decorators,
                'response_model': response_model,
                'returns_raw_model': self._check_returns_raw_model(node),
                'has_enum_serialization': self._check_enum_serialization(node),
                'has_conversion_logic': self._check_conversion_logic(node)
            }
            
            self.endpoints.append(endpoint_info)
            self._validate_endpoint(endpoint_info)
        
        self.generic_visit(node)
    
    def _extract_response_model(self, node: ast.AST) -> Optional[str]:
        """Extract response model name from AST node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Subscript):
            # Handle List[SomeModel], Optional[SomeModel], etc.
            if isinstance(node.slice, ast.Name):
                return node.slice.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_full_name(node.value)}.{node.attr}"
        return None
    
    def _get_full_name(self, node: ast.AST) -> str:
        """Get full name from AST node"""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._get_full_name(node.value)}.{node.attr}"
        return "unknown"
    
    def _check_returns_raw_model(self, func_node: ast.FunctionDef) -> bool:
        """Check if function returns raw SQLAlchemy models"""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and node.value:
                # Look for patterns like "return some_model" or "return query.all()"
                if isinstance(node.value, ast.Name):
                    # Simple return statement
                    return True
                elif isinstance(node.value, ast.Call):
                    if isinstance(node.value.func, ast.Attribute):
                        if node.value.func.attr in ['all', 'first', 'scalar_one', 'scalars']:
                            return True
        return False
    
    def _check_enum_serialization(self, func_node: ast.FunctionDef) -> bool:
        """Check if function properly handles enum serialization"""
        func_source = ast.get_source_segment(open(self.current_file).read(), func_node)
        if func_source:
            # Look for .value calls on potential enum fields
            return '.value' in func_source
        return False
    
    def _check_conversion_logic(self, func_node: ast.FunctionDef) -> bool:
        """Check if function has proper model-to-schema conversion"""
        for node in ast.walk(func_node):
            # Look for response model instantiation
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if 'Response' in node.func.id:
                        return True
        return False
    
    def _validate_endpoint(self, endpoint: Dict):
        """Validate endpoint for common issues"""
        issues = []
        
        # Check for response model without conversion
        if endpoint['response_model'] and endpoint['returns_raw_model']:
            if not endpoint['has_conversion_logic']:
                issues.append({
                    'type': 'raw_model_return',
                    'message': f"Endpoint '{endpoint['name']}' has response_model but may be returning raw SQLAlchemy models. Add conversion logic.",
                    'severity': 'error',
                    'line': endpoint['line'],
                    'suggestion': "Convert SQLAlchemy models to Pydantic response models before returning"
                })
        
        # Check for missing enum serialization
        if endpoint['response_model'] and not endpoint['has_enum_serialization']:
            issues.append({
                'type': 'missing_enum_serialization',
                'message': f"Endpoint '{endpoint['name']}' may not handle enum serialization. Consider using .value for enum fields.",
                'severity': 'warning',
                'line': endpoint['line'],
                'suggestion': "Use enum_field.value to convert enums to strings"
            })
        
        # Check for response model naming consistency
        if endpoint['response_model'] and not endpoint['response_model'].endswith('Response'):
            issues.append({
                'type': 'response_model_naming',
                'message': f"Response model '{endpoint['response_model']}' should end with 'Response' for consistency",
                'severity': 'info',
                'line': endpoint['line']
            })
        
        self.issues.extend(issues)


def check_file(file_path: str) -> List[Dict]:
    """Check a single file for API schema issues"""
    analyzer = APIEndpointAnalyzer()
    return analyzer.analyze_file(file_path)


def main():
    """Main entry point for pre-commit hook"""
    if len(sys.argv) < 2:
        print("Usage: pre_commit_schema_check.py <file1> [file2] ...")
        sys.exit(1)
    
    all_issues = []
    files_checked = 0
    
    for file_path in sys.argv[1:]:
        if not file_path.endswith('.py'):
            continue
        
        if not Path(file_path).exists():
            continue
        
        # Only check API endpoint files
        if '/api/' not in file_path:
            continue
        
        files_checked += 1
        issues = check_file(file_path)
        all_issues.extend(issues)
    
    if not all_issues:
        if files_checked > 0:
            print(f"✅ Schema validation passed for {files_checked} API files")
        sys.exit(0)
    
    # Group issues by severity
    errors = [i for i in all_issues if i['severity'] == 'error']
    warnings = [i for i in all_issues if i['severity'] == 'warning']
    info = [i for i in all_issues if i['severity'] == 'info']
    
    print("🔍 API Schema Validation Issues Found:")
    print("=" * 50)
    
    # Print errors
    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for issue in errors:
            print(f"  {issue.get('message', 'Unknown error')}")
            if 'line' in issue and issue['line'] > 0:
                print(f"     Line: {issue['line']}")
            if 'suggestion' in issue:
                print(f"     💡 {issue['suggestion']}")
            print()
    
    # Print warnings
    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for issue in warnings:
            print(f"  {issue.get('message', 'Unknown warning')}")
            if 'line' in issue and issue['line'] > 0:
                print(f"     Line: {issue['line']}")
            if 'suggestion' in issue:
                print(f"     💡 {issue['suggestion']}")
            print()
    
    # Print info
    if info:
        print(f"\nℹ️  INFO ({len(info)}):")
        for issue in info:
            print(f"  {issue.get('message', 'Unknown info')}")
            if 'line' in issue and issue['line'] > 0:
                print(f"     Line: {issue['line']}")
            print()
    
    # Exit with error code if there are errors
    if errors:
        print("\n🚫 Commit blocked due to schema validation errors.")
        print("Fix the errors above and try again.")
        sys.exit(1)
    else:
        print(f"\n✅ No blocking errors found. {len(warnings)} warnings, {len(info)} info messages.")
        sys.exit(0)


if __name__ == "__main__":
    main()