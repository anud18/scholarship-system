#!/usr/bin/env python3
"""
Quick endpoint schema validation script

Run this script to quickly test all API endpoints for schema validation errors
without having to set up full integration tests.

Usage:
    python test_endpoint_schemas.py
    python test_endpoint_schemas.py --endpoint /api/v1/scholarships/eligible
"""

import argparse
import json
from datetime import datetime
from typing import Any, Dict, List

import requests


class EndpointTester:
    """Test API endpoints for schema validation"""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.test_token = "test-token-for-schema-validation"

    def get_headers(self) -> Dict[str, str]:
        """Get request headers with auth token"""
        return {
            "Authorization": f"Bearer {self.test_token}",
            "Content-Type": "application/json",
        }

    def test_endpoint(
        self, method: str, path: str, data: Dict = None
    ) -> Dict[str, Any]:
        """
        Test a single endpoint

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API endpoint path
            data: Request data for POST/PUT requests

        Returns:
            dict: Test result with status, response, and validation info
        """
        url = f"{self.base_url}{path}"
        headers = self.get_headers()

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=10)
            elif method.upper() == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=10)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                return {"error": f"Unsupported method: {method}"}

            result = {
                "method": method.upper(),
                "path": path,
                "status_code": response.status_code,
                "success": response.status_code < 400,
                "timestamp": datetime.now().isoformat(),
            }

            # Try to parse JSON response
            try:
                response_data = response.json()
                result["response_data"] = response_data
                result["has_json_response"] = True

                # Basic schema checks
                if isinstance(response_data, dict):
                    result["response_fields"] = list(response_data.keys())
                elif isinstance(response_data, list) and response_data:
                    result["response_fields"] = (
                        list(response_data[0].keys()) if response_data else []
                    )
                    result["response_count"] = len(response_data)

            except json.JSONDecodeError:
                result["response_text"] = response.text
                result["has_json_response"] = False

            # Check for specific validation errors
            if "ResponseValidationError" in response.text:
                result["has_validation_error"] = True
                result["validation_error_details"] = self.extract_validation_errors(
                    response.text
                )
            else:
                result["has_validation_error"] = False

            return result

        except requests.exceptions.RequestException as e:
            return {
                "method": method.upper(),
                "path": path,
                "error": str(e),
                "success": False,
                "timestamp": datetime.now().isoformat(),
            }

    def extract_validation_errors(self, error_text: str) -> List[str]:
        """Extract validation error details from error text"""
        errors = []
        lines = error_text.split("\n")

        for line in lines:
            if "'type':" in line and "'loc':" in line and "'msg':" in line:
                # Try to extract the key information from the error
                try:
                    # This is a simplified extraction - in practice you might want more robust parsing
                    if "'missing'" in line:
                        errors.append(f"Missing field: {line}")
                    elif "'string_type'" in line:
                        errors.append(f"Type error: {line}")
                except:
                    errors.append(line.strip())

        return errors

    def test_all_endpoints(self) -> List[Dict[str, Any]]:
        """Test all common API endpoints"""
        endpoints = [
            ("GET", "/health"),
            ("GET", "/api/v1/scholarships/"),
            ("GET", "/api/v1/scholarships/eligible"),
            ("GET", "/api/v1/applications/"),
            ("GET", "/api/v1/users/me"),
        ]

        results = []
        for method, path in endpoints:
            print(f"Testing {method} {path}...")
            result = self.test_endpoint(method, path)
            results.append(result)

            # Print immediate result
            if result.get("success"):
                status = "✅ PASS"
            elif result.get("has_validation_error"):
                status = "❌ SCHEMA ERROR"
            else:
                status = "⚠️  OTHER ERROR"

            print(f"  {status} - Status: {result.get('status_code', 'N/A')}")

            if result.get("has_validation_error"):
                print("  Validation errors:")
                for error in result.get("validation_error_details", []):
                    print(f"    - {error}")

        return results

    def generate_report(self, results: List[Dict[str, Any]]) -> str:
        """Generate a summary report"""
        total = len(results)
        passed = len([r for r in results if r.get("success", False)])
        validation_errors = len(
            [r for r in results if r.get("has_validation_error", False)]
        )

        report = f"""
=== API Schema Validation Report ===
Generated: {datetime.now().isoformat()}

Summary:
- Total endpoints tested: {total}
- Passed: {passed}
- Failed: {total - passed}
- Schema validation errors: {validation_errors}

Detailed Results:
"""

        for result in results:
            status = "PASS" if result.get("success") else "FAIL"
            method = result.get("method", "?")
            path = result.get("path", "?")
            status_code = result.get("status_code", "?")

            report += f"\n{status}: {method} {path} (HTTP {status_code})"

            if result.get("has_validation_error"):
                report += "\n  ❌ SCHEMA VALIDATION ERROR"
                for error in result.get("validation_error_details", []):
                    report += f"\n    {error}"

            if result.get("error"):
                report += f"\n  Error: {result['error']}"

        if validation_errors > 0:
            report += f"""

=== Recommendations ===
Found {validation_errors} schema validation error(s). To fix:

1. Check that response models match the actual data being returned
2. Ensure enum values are converted to strings (use .value)
3. Convert SQLAlchemy models to response schemas
4. Add missing required fields to response models
5. Review the schema validation utilities in app/core/schema_validation.py

"""

        return report


def main():
    parser = argparse.ArgumentParser(
        description="Test API endpoints for schema validation"
    )
    parser.add_argument(
        "--endpoint",
        help="Test specific endpoint (e.g., /api/v1/scholarships/eligible)",
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000", help="Base URL for API"
    )
    parser.add_argument("--output", help="Output file for report")

    args = parser.parse_args()

    tester = EndpointTester(args.base_url)

    if args.endpoint:
        # Test specific endpoint
        print(f"Testing endpoint: {args.endpoint}")
        result = tester.test_endpoint("GET", args.endpoint)

        if result.get("success"):
            print("✅ Endpoint test passed")
        elif result.get("has_validation_error"):
            print("❌ Schema validation error found")
            for error in result.get("validation_error_details", []):
                print(f"  - {error}")
        else:
            print(f"⚠️  Test failed: {result.get('error', 'Unknown error')}")

    else:
        # Test all endpoints
        print("Testing all endpoints...")
        results = tester.test_all_endpoints()

        # Generate report
        report = tester.generate_report(results)

        if args.output:
            with open(args.output, "w") as f:
                f.write(report)
            print(f"\nReport saved to: {args.output}")
        else:
            print(report)


if __name__ == "__main__":
    main()
