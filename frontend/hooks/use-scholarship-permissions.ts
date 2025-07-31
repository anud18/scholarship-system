import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '@/lib/api'
import { ScholarshipPermission } from '@/lib/api'
import { useAuth } from './use-auth'

export function useScholarshipPermissions() {
  const { user, isAuthenticated } = useAuth()
  const [permissions, setPermissions] = useState<ScholarshipPermission[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchPermissions = useCallback(async () => {
    console.log('useScholarshipPermissions: fetchPermissions called for user:', user?.role, user?.id)
    
    if (!isAuthenticated || !user) {
      console.log('useScholarshipPermissions: User not authenticated')
      setPermissions([])
      return
    }

    // Super admin has access to all scholarships by default
    if (user.role === 'super_admin') {
      console.log('useScholarshipPermissions: Super admin - access to all scholarships')
      setPermissions([]) // Empty array means access to all
      return
    }

    // Admin and college roles need specific permissions
    if (!['admin', 'college'].includes(user.role)) {
      console.log('useScholarshipPermissions: User role not eligible for permissions:', user.role)
      setPermissions([])
      return
    }

    try {
      setIsLoading(true)
      setError(null)
      
      console.log('useScholarshipPermissions: Fetching permissions from API...')
      const response = await apiClient.admin.getCurrentUserScholarshipPermissions()
      console.log('useScholarshipPermissions: API response:', response)
      
      if (response.success && response.data) {
        console.log('useScholarshipPermissions: Setting permissions:', response.data)
        setPermissions(response.data)
      } else {
        console.log('useScholarshipPermissions: No permissions data, setting empty array')
        setPermissions([])
      }
    } catch (err) {
      console.error('Failed to fetch scholarship permissions:', err)
      setError('Failed to fetch scholarship permissions')
      setPermissions([])
    } finally {
      setIsLoading(false)
    }
  }, [isAuthenticated, user])

  // Check if user has permission for a specific scholarship
  const hasPermission = useCallback((scholarshipId: number | string): boolean => {
    if (!user) return false
    
    // Super admin has access to all scholarships
    if (user.role === 'super_admin') return true
    
    // Admin and college roles need specific permissions
    if (['admin', 'college'].includes(user.role)) {
      // If permissions array is empty, it means no specific permissions assigned
      if (permissions.length === 0) return false
      
      return permissions.some(permission => 
        permission.scholarship_id === Number(scholarshipId)
      )
    }
    
    return false
  }, [user, permissions])

  // Get allowed scholarship IDs for the current user
  const getAllowedScholarshipIds = useCallback((): number[] => {
    if (!user) return []
    
    // Super admin has access to all scholarships
    if (user.role === 'super_admin') return []
    
    // Admin and college roles need specific permissions
    if (['admin', 'college'].includes(user.role)) {
      return permissions.map(permission => permission.scholarship_id)
    }
    
    return []
  }, [user, permissions])

  // Filter scholarships based on user permissions
  const filterScholarshipsByPermission = useCallback(<T extends { id: number | string }>(scholarships: T[]): T[] => {
    console.log('filterScholarshipsByPermission: Called with scholarships:', scholarships.length)
    console.log('filterScholarshipsByPermission: User role:', user?.role)
    
    if (!user) {
      console.log('filterScholarshipsByPermission: No user, returning empty array')
      return []
    }
    
    // Super admin can see all scholarships
    if (user.role === 'super_admin') {
      console.log('filterScholarshipsByPermission: Super admin, returning all scholarships')
      return scholarships
    }
    
    // Admin and college roles need specific permissions
    if (['admin', 'college'].includes(user.role)) {
      const allowedIds = getAllowedScholarshipIds()
      console.log('filterScholarshipsByPermission: Allowed scholarship IDs:', allowedIds)
      
      // If no specific permissions assigned, return empty array
      if (allowedIds.length === 0) {
        console.log('filterScholarshipsByPermission: No permissions assigned, returning empty array')
        return []
      }
      
      const filtered = scholarships.filter(scholarship => 
        allowedIds.includes(Number(scholarship.id))
      )
      console.log('filterScholarshipsByPermission: Filtered scholarships:', filtered.length)
      return filtered
    }
    
    console.log('filterScholarshipsByPermission: User role not eligible, returning empty array')
    return []
  }, [user, getAllowedScholarshipIds])

  useEffect(() => {
    fetchPermissions()
  }, [fetchPermissions])

  return {
    permissions,
    isLoading,
    error,
    hasPermission,
    getAllowedScholarshipIds,
    filterScholarshipsByPermission,
    refetch: fetchPermissions
  }
} 