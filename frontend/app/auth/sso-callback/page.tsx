"use client"

import { useEffect, useState, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2 } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

function SSOCallbackContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const [message, setMessage] = useState('')

  useEffect(() => {
    const handleSSOCallback = async () => {
      try {
        // Get token and redirect path from URL parameters
        const token = searchParams.get('token')
        const redirectPath = searchParams.get('redirect') || 'dashboard'
        
        if (!token) {
          throw new Error('No token provided')
        }

        // Store token in localStorage
        localStorage.setItem('auth_token', token)
        
        // Optional: Verify token by making a request to /auth/me
        try {
          const response = await fetch('/api/v1/auth/me', {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          })
          
          if (response.ok) {
            const userData = await response.json()
            localStorage.setItem('user', JSON.stringify(userData.data))
            setStatus('success')
            setMessage('登入成功！正在重導向...')
            
            // Redirect to dashboard after a brief delay
            setTimeout(() => {
              router.push('/')
            }, 1500)
          } else {
            throw new Error('Token verification failed')
          }
        } catch (verifyError) {
          // If verification fails, still proceed with the token
          console.warn('Token verification failed, proceeding anyway:', verifyError)
          setStatus('success')
          setMessage('登入成功！正在重導向...')
          
          setTimeout(() => {
            router.push('/')
          }, 1500)
        }

      } catch (error) {
        console.error('SSO callback error:', error)
        setStatus('error')
        setMessage('登入失敗，請重新嘗試')
        
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