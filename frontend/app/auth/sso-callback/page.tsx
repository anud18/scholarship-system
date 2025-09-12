"use client"

import { useEffect, useState, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2 } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { useAuth } from "@/hooks/use-auth"

function SSOCallbackContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { login } = useAuth()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const handleSSOCallback = async () => {
      try {
        // Get token and redirect path from URL parameters
        const token = searchParams.get('token')
        const redirectPath = searchParams.get('redirect') || 'dashboard'
        
        console.log('🔐 SSO Callback - Starting authentication process')
        console.log('📄 URL Search Params:', Object.fromEntries(searchParams.entries()))
        console.log('🎟️ Token received:', !!token, token ? `${token.substring(0, 20)}...` : 'none')
        console.log('🔄 Redirect path:', redirectPath)
        
        if (!token) {
          console.error('❌ No token provided in URL parameters')
          throw new Error('No token provided')
        }

        // Verify token by making a request to /auth/me
        console.log('🌐 Making API request to verify token...')
        console.log('🌍 Environment:', process.env.NODE_ENV)
        console.log('🔗 Base URL config:', process.env.NEXT_PUBLIC_API_URL)
        try {
          // In Docker production, use relative path through nginx proxy
          // In development, use direct backend URL
          let requestUrl: string
          if (process.env.NODE_ENV === 'production') {
            requestUrl = '/api/v1/auth/me'  // Nginx will proxy to backend
            console.log('🏭 Production mode - using nginx proxy path')
          } else {
            const apiUrl = process.env.NEXT_PUBLIC_API_URL || `${window.location.protocol}//${window.location.hostname}:8000`
            requestUrl = `${apiUrl}/api/v1/auth/me`
            console.log('🛠️ Development mode - using direct backend URL')
          }
          console.log('🌐 Final API request URL:', requestUrl)
          
          const response = await fetch(requestUrl, {
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          })
          
          console.log('📡 API Response status:', response.status, response.statusText)
          console.log('📡 API Response headers:', Object.fromEntries(response.headers.entries()))
          
          if (response.ok) {
            const userData = await response.json()
            console.log('👤 User data received:', userData)
            console.log('🔑 User role:', userData.data?.role)
            console.log('📧 User email:', userData.data?.email)
            console.log('🆔 User ID:', userData.data?.id)
            
            // Use the login function from useAuth to properly set authentication state
            console.log('🔄 Calling login() with token and user data...')
            login(token, userData.data)
            console.log('✅ login() function called successfully')
            
            setStatus('success')
            setMessage('登入成功！正在重導向...')
            
            // Redirect based on user role
            const userRole = userData.data?.role
            let redirectPath = '/'
            
            console.log('🎯 Determining redirect path based on role:', userRole)
            
            // Role-based redirection
            if (userRole === 'admin' || userRole === 'super_admin') {
              redirectPath = '/#dashboard'  // Admin dashboard
              console.log('👑 Admin/Super Admin - redirecting to dashboard')
            } else if (userRole === 'professor') {
              redirectPath = '/#main'  // Professor review page
              console.log('🎓 Professor - redirecting to main')
            } else if (userRole === 'college') {
              redirectPath = '/#main'  // College dashboard
              console.log('🏫 College - redirecting to main')
            } else {
              redirectPath = '/#main'  // Student portal
              console.log('🎒 Student - redirecting to main')
            }
            
            console.log('🚀 Final redirect path:', redirectPath)
            console.log('⏰ Setting 1.5 second delay before redirect...')
            
            setTimeout(() => {
              console.log('⏰ Timeout reached, executing router.push...')
              router.push(redirectPath)
              console.log('✅ router.push() called')
            }, 1500)
          } else {
            throw new Error('Token verification failed')
          }
        } catch (verifyError) {
          console.error('💥 Token verification failed:', verifyError)
          console.error('📡 Verification error details:', verifyError instanceof Error ? verifyError.message : verifyError)
          setStatus('error')
          setMessage('登入驗證失敗，請重新嘗試')
          
          console.log('🔄 Redirecting to login page after token verification error')
          // Redirect to login page after error
          setTimeout(() => {
            router.push('/')
          }, 3000)
        }

      } catch (error) {
        console.error('💥 SSO callback error:', error)
        console.error('💥 Error details:', error instanceof Error ? error.message : error)
        console.error('💥 Error stack:', error instanceof Error ? error.stack : 'No stack trace')
        setStatus('error')
        setMessage('登入失敗，請重新嘗試')
        
        console.log('🔄 Redirecting to login page after general error')
        // Redirect to login page after error
        setTimeout(() => {
          router.push('/')
        }, 3000)
      }
    }

    handleSSOCallback()
  }, [router, searchParams])

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl text-nycu-navy-800">
            Portal SSO 登入
          </CardTitle>
          <CardDescription>
            正在處理您的登入請求...
          </CardDescription>
        </CardHeader>
        <CardContent className="text-center">
          {status === 'loading' && (
            <>
              <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
              <p className="text-nycu-navy-600">正在驗證登入資訊...</p>
            </>
          )}
          
          {status === 'success' && (
            <>
              <div className="h-8 w-8 mx-auto mb-4 text-green-600 flex items-center justify-center">
                <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
              </div>
              <p className="text-green-600 font-medium">{message}</p>
            </>
          )}
          
          {status === 'error' && (
            <>
              <div className="h-8 w-8 mx-auto mb-4 text-red-600 flex items-center justify-center">
                <svg className="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </div>
              <p className="text-red-600 font-medium">{message}</p>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

export default function SSOCallbackPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-nycu-blue-50 flex items-center justify-center">
        <Card className="w-full max-w-md">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl text-nycu-navy-800">
              Portal SSO 登入
            </CardTitle>
            <CardDescription>
              正在處理您的登入請求...
            </CardDescription>
          </CardHeader>
          <CardContent className="text-center">
            <Loader2 className="h-8 w-8 animate-spin mx-auto mb-4 text-nycu-blue-600" />
            <p className="text-nycu-navy-600">正在載入頁面...</p>
          </CardContent>
        </Card>
      </div>
    }>
      <SSOCallbackContent />
    </Suspense>
  )
}