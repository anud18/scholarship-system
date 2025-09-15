"use client"

import { useState, useEffect } from 'react'
import { X, Bug, ChevronDown, ChevronRight, Copy, CheckCircle2 } from 'lucide-react'
import { useAuth } from '@/hooks/use-auth'

interface DebugPanelProps {
  isTestMode?: boolean
}

export function DebugPanel({ isTestMode = false }: DebugPanelProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [portalData, setPortalData] = useState<any>(null)
  const [studentData, setStudentData] = useState<any>(null)
  const [jwtData, setJwtData] = useState<any>(null)
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['jwt', 'portal', 'student']))
  const [copiedField, setCopiedField] = useState<string | null>(null)
  const { user, token } = useAuth()

  // Only show in test/development mode
  const shouldShow = isTestMode || process.env.NODE_ENV === 'development' || 
    (typeof window !== 'undefined' && (
      window.location.hostname === '140.113.7.148' || 
      window.location.hostname === 'localhost'
    ))

  useEffect(() => {
    if (!shouldShow || !token) return

    // Decode JWT to get portal data
    try {
      const parts = token.split('.')
      if (parts.length === 3) {
        const payload = JSON.parse(atob(parts[1]))
        setJwtData(payload)
        
        // Extract portal data from JWT
        if (payload.portal_data) {
          setPortalData(payload.portal_data)
        }
        
        // Extract student data from JWT
        if (payload.student_data) {
          setStudentData(payload.student_data)
        }
      }
    } catch (error) {
      console.error('Failed to decode JWT:', error)
    }

    // Try to get data from sessionStorage (if stored by backend)
    const storedPortalData = sessionStorage.getItem('debug_portal_data')
    const storedStudentData = sessionStorage.getItem('debug_student_data')
    
    if (storedPortalData) {
      try {
        setPortalData(JSON.parse(storedPortalData))
      } catch (e) {}
    }
    
    if (storedStudentData) {
      try {
        setStudentData(JSON.parse(storedStudentData))
      } catch (e) {}
    }
  }, [token, shouldShow])

  if (!shouldShow) return null

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(section)) {
      newExpanded.delete(section)
    } else {
      newExpanded.add(section)
    }
    setExpandedSections(newExpanded)
  }

  const copyToClipboard = async (text: string, field: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedField(field)
      setTimeout(() => setCopiedField(null), 2000)
    } catch (error) {
      console.error('Failed to copy:', error)
    }
  }

  const renderValue = (value: any, path: string = ''): JSX.Element => {
    if (value === null || value === undefined) {
      return <span className="text-gray-400">null</span>
    }
    
    if (typeof value === 'boolean') {
      return <span className={value ? 'text-green-600' : 'text-red-600'}>{String(value)}</span>
    }
    
    if (typeof value === 'string' || typeof value === 'number') {
      const stringValue = String(value)
      return (
        <div className="flex items-center gap-1 group">
          <span className="text-blue-600">{stringValue}</span>
          <button
            onClick={() => copyToClipboard(stringValue, path)}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-0.5 hover:bg-gray-100 rounded"
            title="Copy to clipboard"
          >
            {copiedField === path ? (
              <CheckCircle2 className="w-3 h-3 text-green-600" />
            ) : (
              <Copy className="w-3 h-3 text-gray-400" />
            )}
          </button>
        </div>
      )
    }
    
    if (Array.isArray(value)) {
      return (
        <div className="ml-4">
          <span className="text-gray-500">[{value.length} items]</span>
          {value.map((item, index) => (
            <div key={index} className="ml-2 my-1">
              <span className="text-gray-400">{index}:</span> {renderValue(item, `${path}[${index}]`)}
            </div>
          ))}
        </div>
      )
    }
    
    if (typeof value === 'object') {
      return (
        <div className="ml-4">
          {Object.entries(value).map(([key, val]) => (
            <div key={key} className="my-1">
              <span className="text-purple-600">{key}:</span> {renderValue(val, `${path}.${key}`)}
            </div>
          ))}
        </div>
      )
    }
    
    return <span className="text-gray-600">{JSON.stringify(value)}</span>
  }

  return (
    <>
      {/* Floating Debug Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="fixed bottom-4 right-4 z-50 bg-orange-500 hover:bg-orange-600 text-white rounded-full p-3 shadow-lg transition-all duration-200 group"
        title="Debug Panel"
      >
        <Bug className="w-5 h-5" />
        <span className="absolute -top-2 -right-2 bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center animate-pulse">
          {isTestMode ? 'T' : 'D'}
        </span>
      </button>

      {/* Debug Panel */}
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => setIsOpen(false)}>
          <div 
            className="bg-white rounded-lg shadow-xl w-[90%] max-w-4xl h-[80vh] flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b bg-gray-50">
              <div className="flex items-center gap-2">
                <Bug className="w-5 h-5 text-orange-500" />
                <h2 className="text-lg font-semibold">Debug Panel - API Data Inspector</h2>
                <span className="text-xs bg-orange-100 text-orange-700 px-2 py-1 rounded">
                  {isTestMode ? 'TEST MODE' : 'DEV MODE'}
                </span>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 hover:bg-gray-200 rounded transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {/* Current User Info */}
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                  <span className="font-semibold text-sm">Current User</span>
                </div>
                {user ? (
                  <div className="text-sm space-y-1">
                    <div>ID: <span className="font-mono text-blue-600">{user.id}</span></div>
                    <div>Email: <span className="font-mono text-blue-600">{user.email}</span></div>
                    <div>Role: <span className="font-mono text-blue-600">{user.role}</span></div>
                    <div>NYCU ID: <span className="font-mono text-blue-600">{user.nycu_id || 'N/A'}</span></div>
                  </div>
                ) : (
                  <div className="text-gray-500 text-sm">No user logged in</div>
                )}
              </div>

              {/* JWT Token Data */}
              <div className="border rounded-lg">
                <button
                  onClick={() => toggleSection('jwt')}
                  className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <span className="font-semibold">JWT Token Data</span>
                  {expandedSections.has('jwt') ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </button>
                {expandedSections.has('jwt') && (
                  <div className="p-4 bg-gray-50">
                    {jwtData ? (
                      <div className="font-mono text-xs overflow-x-auto">
                        {renderValue(jwtData)}
                      </div>
                    ) : (
                      <div className="text-gray-500">No JWT data available</div>
                    )}
                  </div>
                )}
              </div>

              {/* Portal SSO Data */}
              <div className="border rounded-lg">
                <button
                  onClick={() => toggleSection('portal')}
                  className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <span className="font-semibold">Portal SSO Data</span>
                  {expandedSections.has('portal') ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </button>
                {expandedSections.has('portal') && (
                  <div className="p-4 bg-gray-50">
                    {portalData ? (
                      <div className="font-mono text-xs overflow-x-auto">
                        {renderValue(portalData)}
                      </div>
                    ) : (
                      <div className="text-gray-500">No Portal data available</div>
                    )}
                  </div>
                )}
              </div>

              {/* Student API Data */}
              <div className="border rounded-lg">
                <button
                  onClick={() => toggleSection('student')}
                  className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <span className="font-semibold">Student API Data</span>
                  {expandedSections.has('student') ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </button>
                {expandedSections.has('student') && (
                  <div className="p-4 bg-gray-50">
                    {studentData ? (
                      <div className="font-mono text-xs overflow-x-auto">
                        {renderValue(studentData)}
                      </div>
                    ) : (
                      <div className="text-gray-500">No Student API data available</div>
                    )}
                  </div>
                )}
              </div>

              {/* Environment Info */}
              <div className="border rounded-lg">
                <button
                  onClick={() => toggleSection('env')}
                  className="w-full px-4 py-3 flex items-center justify-between bg-gray-50 hover:bg-gray-100 transition-colors"
                >
                  <span className="font-semibold">Environment Info</span>
                  {expandedSections.has('env') ? (
                    <ChevronDown className="w-4 h-4" />
                  ) : (
                    <ChevronRight className="w-4 h-4" />
                  )}
                </button>
                {expandedSections.has('env') && (
                  <div className="p-4 bg-gray-50 font-mono text-xs">
                    <div>NODE_ENV: <span className="text-blue-600">{process.env.NODE_ENV}</span></div>
                    <div>API URL: <span className="text-blue-600">{process.env.NEXT_PUBLIC_API_URL || 'Not set'}</span></div>
                    <div>Host: <span className="text-blue-600">{typeof window !== 'undefined' ? window.location.host : 'N/A'}</span></div>
                    <div>Protocol: <span className="text-blue-600">{typeof window !== 'undefined' ? window.location.protocol : 'N/A'}</span></div>
                    <div>User Agent: <span className="text-blue-600 text-xs">{typeof window !== 'undefined' ? navigator.userAgent : 'N/A'}</span></div>
                  </div>
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="p-4 border-t bg-gray-50 text-xs text-gray-600">
              <div className="flex items-center justify-between">
                <span>Debug panel active in test/development mode</span>
                <span>Last updated: {new Date().toLocaleTimeString()}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  )
}