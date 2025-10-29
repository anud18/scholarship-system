#!/bin/bash

# College Review API Test Script
# Tests the fixed unified review system

set -e

echo "========================================="
echo "Testing College Review API"
echo "========================================="
echo ""

# College user token (from seed data)
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMSIsIm55Y3VfaWQiOiJjc19jb2xsZWdlIiwicm9sZSI6ImNvbGxlZ2UiLCJkZWJ1Z19tb2RlIjp0cnVlLCJleHAiOjE3NjA2MDc1OTd9.XR-tutC7N5G_rUbkXoWyGsE6DEhNtSQa_D8UBFoKUMo"

BASE_URL="http://localhost:8000/api/v1"

# Step 1: Get applications for review
echo "Step 1: Getting applications for college review..."
APPS_RESPONSE=$(curl -s "${BASE_URL}/college-review/applications" \
  -H "Authorization: Bearer $TOKEN")

echo "Applications response:"
echo "$APPS_RESPONSE" | jq -r '.success, .message, (.data | length)'
echo ""

# Extract first application ID
APP_ID=$(echo "$APPS_RESPONSE" | jq -r '.data[0].id // empty')

if [ -z "$APP_ID" ]; then
  echo "❌ No applications found for review. Please ensure there are applications in 'recommended' status."
  exit 1
fi

echo "✓ Found application ID: $APP_ID"
echo ""

# Step 2: Get sub-types for the application
echo "Step 2: Getting sub-types for application $APP_ID..."
SUBTYPES_RESPONSE=$(curl -s "${BASE_URL}/college-review/applications/${APP_ID}/sub-types" \
  -H "Authorization: Bearer $TOKEN")

echo "Sub-types response:"
echo "$SUBTYPES_RESPONSE" | jq -r '.success, .message, .data'
echo ""

SUBTYPES=$(echo "$SUBTYPES_RESPONSE" | jq -r '.data[]')

if [ -z "$SUBTYPES" ]; then
  echo "❌ No sub-types found for application"
  exit 1
fi

echo "✓ Found sub-types: $SUBTYPES"
echo ""

# Step 3: Submit review using unified review system
echo "Step 3: Submitting college review..."

# Build items array
ITEMS_JSON=$(echo "$SUBTYPES" | jq -R -s -c 'split("\n") | map(select(length > 0)) | map({sub_type_code: ., recommendation: "approve", comments: "測試核准"})')

REVIEW_DATA=$(jq -n --argjson items "$ITEMS_JSON" '{items: $items}')

echo "Review data to submit:"
echo "$REVIEW_DATA" | jq '.'
echo ""

REVIEW_RESPONSE=$(curl -s -X POST "${BASE_URL}/college-review/applications/${APP_ID}/review" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$REVIEW_DATA")

echo "Review submission response:"
echo "$REVIEW_RESPONSE" | jq '.'
echo ""

# Check if review was successful
SUCCESS=$(echo "$REVIEW_RESPONSE" | jq -r '.success')

if [ "$SUCCESS" = "true" ]; then
  echo "========================================="
  echo "✅ SUCCESS: College review submitted successfully!"
  echo "========================================="

  # Check redistribution info
  REDISTRIBUTION=$(echo "$REVIEW_RESPONSE" | jq -r '.data.redistribution_info // empty')
  if [ -n "$REDISTRIBUTION" ]; then
    echo ""
    echo "Auto-redistribution information:"
    echo "$REVIEW_RESPONSE" | jq -r '.data.redistribution_info'
  fi
else
  echo "========================================="
  echo "❌ FAILED: Review submission failed"
  echo "========================================="
  ERROR_MSG=$(echo "$REVIEW_RESPONSE" | jq -r '.message // "Unknown error"')
  echo "Error: $ERROR_MSG"
  exit 1
fi
