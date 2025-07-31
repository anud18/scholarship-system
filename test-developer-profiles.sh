#!/bin/bash

# Developer Profile System Test Script
# Tests personalized developer authentication and profile management

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Configuration
API_BASE="http://localhost:8000/api/v1"
FRONTEND_URL="http://localhost:3000"
DEVELOPER_ID="${1:-$(whoami)}"  # Use provided developer ID or current username

# Helper functions
print_header() {
    echo -e "\n${BLUE}======================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================${NC}"
}

print_step() {
    echo -e "\n${CYAN}➤ $1${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

check_api_response() {
    local response="$1"
    local expected_success="$2"
    
    if echo "$response" | jq -e '.success' > /dev/null 2>&1; then
        local success=$(echo "$response" | jq -r '.success')
        if [ "$success" = "$expected_success" ]; then
            return 0
        fi
    fi
    return 1
}

# Test functions
test_system_availability() {
    print_header "Testing System Availability"
    
    print_step "Checking backend availability..."
    if curl -s "$API_BASE/health" > /dev/null 2>&1; then
        print_success "Backend is running"
    else
        print_error "Backend is not running. Please start with: ./test-docker.sh start"
        exit 1
    fi
    
    print_step "Checking mock SSO availability..."
    response=$(curl -s "$API_BASE/auth/mock-sso/users")
    if check_api_response "$response" "true"; then
        print_success "Mock SSO is enabled"
    else
        print_error "Mock SSO is not available. Check ENABLE_MOCK_SSO setting"
        exit 1
    fi
    
    print_step "Checking frontend availability..."
    if curl -s "$FRONTEND_URL" > /dev/null 2>&1; then
        print_success "Frontend is running"
    else
        print_warning "Frontend might not be running (this is optional for API testing)"
    fi
}

test_developer_profile_creation() {
    print_header "Testing Developer Profile Creation"
    
    print_step "Testing quick setup for developer: $DEVELOPER_ID"
    response=$(curl -s -X POST "$API_BASE/auth/dev-profiles/$DEVELOPER_ID/quick-setup")
    
    if check_api_response "$response" "true"; then
        local count=$(echo "$response" | jq -r '.data.count')
        print_success "Quick setup completed - $count profiles created"
        
        # Show created profiles
        echo -e "\n${PURPLE}Created profiles:${NC}"
        echo "$response" | jq -r '.data.created_profiles[] | "  - \(.username) (\(.role)): \(.full_name)"'
    else
        print_error "Quick setup failed"
        echo "$response" | jq -r '.message // "Unknown error"'
    fi
}

test_custom_profile_creation() {
    print_header "Testing Custom Profile Creation"
    
    print_step "Creating custom student profile for $DEVELOPER_ID"
    
    custom_profile='{
        "full_name": "'$DEVELOPER_ID' Custom Student",
        "chinese_name": "'$DEVELOPER_ID'自定義學生",
        "english_name": "'$DEVELOPER_ID' Custom Student",
        "role": "student",
        "email_domain": "custom.dev",
        "custom_attributes": {
            "gpa": 3.9,
            "major": "Computer Science",
            "special_needs": "Custom testing profile"
        }
    }'
    
    response=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "$custom_profile" \
        "$API_BASE/auth/dev-profiles/$DEVELOPER_ID/create-custom")
    
    if check_api_response "$response" "true"; then
        local username=$(echo "$response" | jq -r '.data.username')
        print_success "Custom profile created: $username"
    else
        print_error "Custom profile creation failed"
        echo "$response" | jq -r '.message // "Unknown error"'
    fi
}

test_student_suite_creation() {
    print_header "Testing Student Suite Creation"
    
    print_step "Creating comprehensive student suite for $DEVELOPER_ID"
    response=$(curl -s -X POST "$API_BASE/auth/dev-profiles/$DEVELOPER_ID/student-suite")
    
    if check_api_response "$response" "true"; then
        local count=$(echo "$response" | jq -r '.data.count')
        print_success "Student suite created - $count profiles"
        
        echo -e "\n${PURPLE}Student profiles:${NC}"
        echo "$response" | jq -r '.data.created_profiles[] | "  - \(.username) (\(.student_type)): \(.full_name)"'
    else
        print_error "Student suite creation failed"
        echo "$response" | jq -r '.message // "Unknown error"'
    fi
}

test_staff_suite_creation() {
    print_header "Testing Staff Suite Creation"
    
    print_step "Creating staff suite for $DEVELOPER_ID"
    response=$(curl -s -X POST "$API_BASE/auth/dev-profiles/$DEVELOPER_ID/staff-suite")
    
    if check_api_response "$response" "true"; then
        local count=$(echo "$response" | jq -r '.data.count')
        print_success "Staff suite created - $count profiles"
        
        echo -e "\n${PURPLE}Staff profiles:${NC}"
        echo "$response" | jq -r '.data.created_profiles[] | "  - \(.username) (\(.role)): \(.full_name)"'
    else
        print_error "Staff suite creation failed"
        echo "$response" | jq -r '.message // "Unknown error"'
    fi
}

test_profile_listing() {
    print_header "Testing Profile Listing"
    
    print_step "Fetching all profiles for $DEVELOPER_ID"
    response=$(curl -s "$API_BASE/auth/dev-profiles/$DEVELOPER_ID")
    
    if check_api_response "$response" "true"; then
        local count=$(echo "$response" | jq -r '.data.count')
        print_success "Found $count profiles for $DEVELOPER_ID"
        
        echo -e "\n${PURPLE}All profiles:${NC}"
        echo "$response" | jq -r '.data.profiles[] | "  - \(.username) (\(.role)): \(.full_name) <\(.email)>"'
    else
        print_error "Profile listing failed"
        echo "$response" | jq -r '.message // "Unknown error"'
    fi
    
    print_step "Fetching all developer IDs"
    response=$(curl -s "$API_BASE/auth/dev-profiles/developers")
    
    if check_api_response "$response" "true"; then
        print_success "Developer IDs retrieved"
        echo -e "\n${PURPLE}All developers:${NC}"
        echo "$response" | jq -r '.data[] | "  - \(.)"'
    else
        print_error "Developer listing failed"
    fi
}

test_authentication_flow() {
    print_header "Testing Authentication Flow"
    
    # Get profiles for testing
    profiles_response=$(curl -s "$API_BASE/auth/dev-profiles/$DEVELOPER_ID")
    
    if ! check_api_response "$profiles_response" "true"; then
        print_error "Cannot fetch profiles for authentication test"
        return
    fi
    
    # Test login with different roles
    echo "$profiles_response" | jq -r '.data.profiles[] | .username' | head -3 | while read username; do
        print_step "Testing login as $username"
        
        login_response=$(curl -s -X POST \
            -H "Content-Type: application/json" \
            -d "{\"username\": \"$username\"}" \
            "$API_BASE/auth/mock-sso/login")
        
        if check_api_response "$login_response" "true"; then
            local access_token=$(echo "$login_response" | jq -r '.data.access_token')
            local user_role=$(echo "$login_response" | jq -r '.data.user.role')
            print_success "Login successful as $username ($user_role)"
            
            # Test authenticated endpoint
            auth_test=$(curl -s -H "Authorization: Bearer $access_token" "$API_BASE/users/me")
            if check_api_response "$auth_test" "true"; then
                local user_name=$(echo "$auth_test" | jq -r '.data.full_name')
                print_success "Authenticated endpoint test passed: $user_name"
            else
                print_error "Authenticated endpoint test failed"
            fi
        else
            print_error "Login failed for $username"
            echo "$login_response" | jq -r '.message // "Unknown error"'
        fi
    done
}

test_profile_cleanup() {
    print_header "Testing Profile Cleanup (Optional)"
    
    echo -e "${YELLOW}This will delete all profiles for $DEVELOPER_ID${NC}"
    read -p "Do you want to test profile cleanup? (y/N): " confirm
    
    if [[ $confirm =~ ^[Yy]$ ]]; then
        print_step "Deleting all profiles for $DEVELOPER_ID"
        response=$(curl -s -X DELETE "$API_BASE/auth/dev-profiles/$DEVELOPER_ID")
        
        if check_api_response "$response" "true"; then
            local deleted_count=$(echo "$response" | jq -r '.data.deleted_count')
            print_success "Deleted $deleted_count profiles"
        else
            print_error "Profile cleanup failed"
            echo "$response" | jq -r '.message // "Unknown error"'
        fi
    else
        print_warning "Skipping profile cleanup"
    fi
}

test_frontend_integration() {
    print_header "Testing Frontend Integration"
    
    if ! curl -s "$FRONTEND_URL" > /dev/null 2>&1; then
        print_warning "Frontend not available - skipping UI tests"
        return
    fi
    
    print_step "Frontend Developer Profile Manager should be visible at:"
    echo -e "${CYAN}$FRONTEND_URL${NC}"
    
    print_step "Testing instructions:"
    echo "1. Open the above URL in your browser"
    echo "2. Look for 'Developer Profile Manager' section below the login form"
    echo "3. Enter your developer ID: $DEVELOPER_ID"
    echo "4. Try the Quick Actions, Custom Profile, and Manage Profiles tabs"
    echo "5. Test one-click login with created profiles"
    
    read -p "Press Enter to automatically open browser (if available)..."
    
    # Try to open browser (works on most systems)
    if command -v xdg-open > /dev/null; then
        xdg-open "$FRONTEND_URL"
    elif command -v open > /dev/null; then
        open "$FRONTEND_URL"
    elif command -v start > /dev/null; then
        start "$FRONTEND_URL"
    else
        print_warning "Cannot automatically open browser. Please visit $FRONTEND_URL manually"
    fi
}

show_usage() {
    echo "Developer Profile System Test Script"
    echo ""
    echo "Usage: $0 [developer_id] [test_type]"
    echo ""
    echo "Arguments:"
    echo "  developer_id    Your unique developer identifier (default: current username)"
    echo "  test_type       Type of test to run (default: full)"
    echo ""
    echo "Test Types:"
    echo "  full           Run all tests (default)"
    echo "  api            Test API endpoints only"
    echo "  create         Test profile creation only"
    echo "  auth           Test authentication flow only"
    echo "  ui             Test frontend integration only"
    echo "  cleanup        Delete all developer profiles"
    echo ""
    echo "Examples:"
    echo "  $0                    # Test with current username"
    echo "  $0 alice             # Test with developer ID 'alice'"
    echo "  $0 alice api         # Test API endpoints for alice"
    echo "  $0 bob cleanup       # Delete all profiles for bob"
    echo ""
    echo "Prerequisites:"
    echo "  - Docker services running (./test-docker.sh start)"
    echo "  - ENABLE_MOCK_SSO=true in environment"
    echo "  - jq installed for JSON parsing"
}

# Main execution
main() {
    local test_type="${2:-full}"
    
    # Check if help requested
    if [[ "$1" == "--help" || "$1" == "-h" ]]; then
        show_usage
        exit 0
    fi
    
    # Check dependencies
    if ! command -v jq > /dev/null; then
        print_error "jq is required for JSON parsing. Please install it:"
        echo "  Ubuntu/Debian: sudo apt-get install jq"
        echo "  macOS: brew install jq"
        echo "  CentOS/RHEL: sudo yum install jq"
        exit 1
    fi
    
    print_header "Developer Profile System Test"
    echo -e "${PURPLE}Developer ID: $DEVELOPER_ID${NC}"
    echo -e "${PURPLE}Test Type: $test_type${NC}"
    echo -e "${PURPLE}API Base: $API_BASE${NC}"
    
    case $test_type in
        "full")
            test_system_availability
            test_developer_profile_creation
            test_custom_profile_creation
            test_student_suite_creation
            test_staff_suite_creation
            test_profile_listing
            test_authentication_flow
            test_frontend_integration
            test_profile_cleanup
            ;;
        "api")
            test_system_availability
            test_developer_profile_creation
            test_custom_profile_creation
            test_student_suite_creation
            test_staff_suite_creation
            test_profile_listing
            ;;
        "create")
            test_system_availability
            test_developer_profile_creation
            test_custom_profile_creation
            test_student_suite_creation
            test_staff_suite_creation
            ;;
        "auth")
            test_system_availability
            test_authentication_flow
            ;;
        "ui")
            test_frontend_integration
            ;;
        "cleanup")
            test_system_availability
            test_profile_cleanup
            ;;
        *)
            print_error "Unknown test type: $test_type"
            show_usage
            exit 1
            ;;
    esac
    
    print_header "Test Summary"
    print_success "Developer profile system testing completed for: $DEVELOPER_ID"
    echo -e "\n${PURPLE}Next Steps:${NC}"
    echo "1. Use created profiles for development and testing"
    echo "2. Each developer has their own isolated test environment"
    echo "3. Profiles persist across development sessions"
    echo "4. All profiles use password: dev123456"
    echo "5. Access frontend at: $FRONTEND_URL"
    
    if [[ $test_type != "cleanup" ]]; then
        echo -e "\n${YELLOW}To clean up profiles later, run:${NC}"
        echo "  $0 $DEVELOPER_ID cleanup"
    fi
}

# Run main function with all arguments
main "$@" 