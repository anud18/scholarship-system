#!/usr/bin/env node

/**
 * Test script to verify API connectivity before running the frontend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function testApiConnection() {
  console.log('🔗 Testing API connectivity...')
  console.log(`📍 API URL: ${API_URL}`)

  try {
    const response = await fetch(`${API_URL}/health`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    })

    if (response.ok) {
      const data = await response.json()
      console.log('✅ API connection successful!')
      console.log('📊 API Status:', data)
      return true
    } else {
      console.log('❌ API connection failed!')
      console.log('📊 Response status:', response.status)
      console.log('📊 Response text:', await response.text())
      return false
    }
  } catch (error) {
    console.log('❌ API connection error!')
    console.log('📊 Error:', error.message)
    console.log('')
    console.log('💡 Make sure the backend server is running on:', API_URL)
    console.log('💡 You can start it with: cd backend && python -m uvicorn app.main:app --reload')
    return false
  }
}

// Run the test
testApiConnection()
  .then(success => {
    if (success) {
      console.log('')
      console.log('🚀 Ready to start the frontend!')
      console.log('💻 Run: npm run dev')
    } else {
      console.log('')
      console.log('⚠️  Please fix the API connection before starting the frontend')
      process.exit(1)
    }
  })
  .catch(error => {
    console.error('Test failed:', error)
    process.exit(1)
  })
