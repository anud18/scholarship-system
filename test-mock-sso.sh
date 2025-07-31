#!/bin/bash

# Mock SSO Testing Script for Docker Environment
# This script tests the mock SSO functionality in the scholarship system

set -e  # Exit on any error

echo "🔐 Mock SSO Testing Script"
echo "=========================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_test() {
    echo -e "${PURPLE}[TEST]${NC} $1"
}

# API base URL
API_URL="http://localhost:8000"
FRONTEND_URL="http://localhost:3000"

# Function to wait for service
wait_for_service() {
    local url=$1
    local service_name=$2
    local max_attempts=30
    local attempt=1

    echo -n "Waiting for $service_name"
    while [ $attempt -le $max_attempts ]; do
        if curl -s "$url" > /dev/null 2>&1; then
            echo ""
            print_success "$service_name is ready"
            return 0
        fi
        echo -n "."
        sleep 2
        ((attempt++))
    done
    
    echo ""
    print_error "$service_name failed to start after $max_attempts attempts"
    return 1
}

# Function to test API endpoint
test_api_endpoint() {
    local method=$1
    local endpoint=$2
    local expected_status=$3
    local data=$4
    local description=$5

    print_test "$description"
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "%{http_code}" -o /tmp/api_response.json "$API_URL$endpoint")
    else
        response=$(curl -s -w "%{http_code}" -o /tmp/api_response.json \
            -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "$API_URL$endpoint")
    fi
    
    if [ "$response" = "$expected_status" ]; then
        print_success "✓ $description (Status: $response)"
        if [ -f /tmp/api_response.json ]; then
            echo "   Response: $(cat /tmp/api_response.json | jq -r '.message // .detail // "Success"' 2>/dev/null || echo "OK")"
        fi
        return 0
    else
        print_error "✗ $description (Expected: $expected_status, Got: $response)"
        if [ -f /tmp/api_response.json ]; then
            echo "   Response: $(cat /tmp/api_response.json)"
        fi
        return 1
    fi
}

# Function to test mock SSO login and return token
test_mock_login() {
    local username=$1
    local expected_role=$2
    
    print_test "Testing mock SSO login for $username ($expected_role)"
    
    # Perform login
    response=$(curl -s -w "%{http_code}" -o /tmp/login_response.json \
        -X POST \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"$username\"}" \
        "$API_URL/api/v1/auth/mock-sso/login")
    
    if [ "$response" = "200" ]; then
        # Extract token and user info
        token=$(cat /tmp/login_response.json | jq -r '.data.access_token')
        user_role=$(cat /tmp/login_response.json | jq -r '.data.user.role')
        user_name=$(cat /tmp/login_response.json | jq -r '.data.user.full_name')
        
        if [ "$user_role" = "$expected_role" ]; then
            print_success "✓ Login successful: $user_name ($user_role)"
            echo "$token" > /tmp/auth_token_$username.txt
            return 0
        else
            print_error "✗ Role mismatch. Expected: $expected_role, Got: $user_role"
            return 1
        fi
    else
        print_error "✗ Login failed (Status: $response)"
        cat /tmp/login_response.json
        return 1
    fi
}

# Function to test authenticated endpoint
test_authenticated_endpoint() {
    local username=$1
    local endpoint=$2
    local description=$3
    
    if [ ! -f "/tmp/auth_token_$username.txt" ]; then
        print_error "No auth token found for $username"
        return 1
    fi
    
    token=$(cat /tmp/auth_token_$username.txt)
    
    print_test "$description"
    
    response=$(curl -s -w "%{http_code}" -o /tmp/auth_response.json \
        -H "Authorization: Bearer $token" \
        "$API_URL$endpoint")
    
    if [ "$response" = "200" ]; then
        print_success "✓ $description"
        return 0
    else
        print_error "✗ $description (Status: $response)"
        cat /tmp/auth_response.json
        return 1
    fi
}

# Main testing function
run_mock_sso_tests() {
    echo ""
    print_status "🧪 Starting Mock SSO Tests"
    echo "================================"
    
    # Test 1: Check if services are running
    print_status "Step 1: Checking service availability"
    wait_for_service "$API_URL/health" "Backend API" || exit 1
    wait_for_service "$FRONTEND_URL" "Frontend" || exit 1
    
    echo ""
    print_status "Step 2: Testing Mock SSO API endpoints"
    
    # Test 2: Get mock users list
    test_api_endpoint "GET" "/api/v1/auth/mock-sso/users" "200" "" "Get mock users list"
    
    # Test 3: Initialize mock users
    
    echo ""
    print_status "Step 3: Testing mock SSO login for different roles"
    
    # Test 4: Login as different users
    test_mock_login "student001" "student"
    test_mock_login "prof001" "professor"
    test_mock_login "college001" "college"
    test_mock_login "admin001" "admin"
    test_mock_login "superadmin" "super_admin"
    
    echo ""
    print_status "Step 4: Testing authenticated endpoints"
    
    # Test 5: Test authenticated endpoints with different roles
    test_authenticated_endpoint "student001" "/api/v1/auth/me" "Student access to profile"
    test_authenticated_endpoint "admin001" "/api/v1/auth/me" "Admin access to profile"
    
    # Test 6: Test role-specific endpoints
    test_authenticated_endpoint "admin001" "/api/v1/admin/dashboard/stats" "Admin dashboard access"
    
    echo ""
    print_status "Step 5: Testing invalid scenarios"
    
    # Test 7: Invalid login
    test_api_endpoint "POST" "/api/v1/auth/mock-sso/login" "400" '{"username": "nonexistent"}' "Invalid user login"
    
    # Test 8: Missing username
    test_api_endpoint "POST" "/api/v1/auth/mock-sso/login" "400" '{}' "Missing username"
    
    echo ""
    print_success "🎉 Mock SSO Tests Completed!"
}

# Function to open browser and test UI
test_frontend_ui() {
    echo ""
    print_status "🌐 Frontend UI Testing Instructions"
    echo "===================================="
    
    print_status "1. Open your browser and navigate to: $FRONTEND_URL"
    print_status "2. You should see the login page with Mock SSO section below the regular login form"
    print_status "3. Click 'Initialize Mock Users' button"
    print_status "4. Try logging in as different users:"
    
    echo ""
    echo "   👨‍🎓 Students:"
    echo "   - student001 (張小明) - Undergraduate student"
    echo "   - student002 (李美華) - Graduate student"
    echo "   - student003 (王大偉) - PhD student"
    echo ""
    echo "   👨‍🏫 Professors:"
    echo "   - prof001 (陳志明) - Computer Science Professor"
    echo "   - prof002 (林雅惠) - Mathematics Professor"
    echo ""
    echo "   🏢 College/Admin:"
    echo "   - college001 (張審核) - Engineering College Reviewer"
    echo "   - admin001 (管理員) - System Administrator"
    echo "   - superadmin (超級管理員) - Super Administrator"
    
    echo ""
    print_status "5. After login, verify that the correct dashboard appears for each role"
    print_status "6. Test role-specific functionality for each user type"
    
    # Ask if user wants to open browser automatically
    read -p "Would you like to open the frontend in your default browser? (y/N): " open_browser
    if [[ $open_browser =~ ^[Yy]$ ]]; then
        if command -v xdg-open > /dev/null; then
            xdg-open "$FRONTEND_URL"
        elif command -v open > /dev/null; then
            open "$FRONTEND_URL"
        else
            print_warning "Could not detect browser command. Please manually open: $FRONTEND_URL"
        fi
    fi
}

# Function to show test summary
show_test_summary() {
    echo ""
    print_status "📋 Test Summary"
    echo "==============="
    echo "Backend API: $API_URL"
    echo "Frontend UI: $FRONTEND_URL"
    echo "API Documentation: $API_URL/docs"
    echo ""
    echo "Mock Users Available:"
    echo "- 3 Students (student001-003)"
    echo "- 2 Professors (prof001-002)"
    echo "- 1 College Reviewer (college001)"
    echo "- 1 Admin (admin001)"
    echo "- 1 Super Admin (superadmin)"
    echo ""
    echo "All users use password: dev123456"
    echo "Or use Mock SSO for one-click login!"
}

# Cleanup function
cleanup_test_files() {
    rm -f /tmp/api_response.json /tmp/login_response.json /tmp/auth_response.json
    rm -f /tmp/auth_token_*.txt
}

# Main script logic
case "${1:-}" in
    "api")
        cleanup_test_files
        run_mock_sso_tests
        show_test_summary
        ;;
    "ui")
        test_frontend_ui
        ;;
    "full")
        cleanup_test_files
        run_mock_sso_tests
        test_frontend_ui
        show_test_summary
        ;;
    *)
        echo "Usage: $0 {api|ui|full}"
        echo ""
        echo "Commands:"
        echo "  api   - Test Mock SSO API endpoints only"
        echo "  ui    - Instructions for testing frontend UI"
        echo "  full  - Run both API tests and UI instructions"
        echo ""
        echo "Make sure the system is running with: ./test-docker.sh start"
        exit 1
        ;;
esac

cleanup_test_files 