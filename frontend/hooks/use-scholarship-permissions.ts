import { useState, useEffect, useCallback } from 'react'
import { apiClient } from '@/lib/api'
import { ScholarshipPermission } from '@/lib/api'
import { useAuth } from './use-auth'

interface AllowedScholarship {
  id: number
  name: string
  name_en?: string
  code: string
  category?: string
  application_cycle?: string
  amount?: number
  status?: string
}

export function useScholarshipPermissions() {
  const { user, isAuthenticated } = useAuth()
  const [permissions, setPermissions] = useState<ScholarshipPermission[]>([])
  const [allowedScholarships, setAllowedScholarships] = useState<AllowedScholarship[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchPermissions = useCallback(async () => {
    console.log('useScholarshipPermissions: fetchPermissions called for user:', user?.role, user?.id)
    
    if (!isAuthenticated || !user) {
      console.log('useScholarshipPermissions: User not authenticated')
      setPermissions([])
      setAllowedScholarships([])
      return
    }

    // Only admin and super_admin roles can have scholarship permissions
    if (!['admin', 'super_admin'].includes(user.role)) {
      console.log('useScholarshipPermissions: User role not eligible for permissions:', user.role)
      setPermissions([])
      setAllowedScholarships([])
      return
    }

    try {
      setIsLoading(true)
      setError(null)
      
      console.log('useScholarshipPermissions: Fetching allowed scholarships from API...')
      const response = await apiClient.admin.getMyScholarships()
      console.log('useScholarshipPermissions: API response:', response)
      
      if (response.success && response.data) {
        console.log('useScholarshipPermissions: Setting allowed scholarships:', response.data)
        setAllowedScholarships(response.data)
        
        // Convert to permission format for backward compatibility
        const nowIso = new Date().toISOString()
        const permissionList = response.data.map(scholarship => ({
          id: scholarship.id,
          user_id: Number(user.id),
          scholarship_id: scholarship.id,
          scholarship_name: scholarship.name,
          scholarship_name_en: scholarship.name_en,
          created_at: nowIso,
          updated_at: nowIso
        }))
        setPermissions(permissionList)
      } else {
        console.log('useScholarshipPermissions: No scholarship data, setting empty array')
        setPermissions([])
        setAllowedScholarships([])
      }
    } catch (err) {
      console.error('Failed to fetch allowed scholarships:', err)
      setError('Failed to fetch allowed scholarships')
      setPermissions([])
      setAllowedScholarships([])
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
      // If allowedScholarships array is empty, it means no specific permissions assigned
      if (allowedScholarships.length === 0) return false
      
      return allowedScholarships.some(scholarship => 
        scholarship.id === Number(scholarshipId)
      )
    }
    
    return false
  }, [user, allowedScholarships])

  // Get allowed scholarship IDs for the current user
  const getAllowedScholarshipIds = useCallback((): number[] => {
    if (!user) return []
    
    // Super admin has access to all scholarships (return empty array to indicate "all")
    if (user.role === 'super_admin') return []
    
    // Admin and college roles need specific permissions
    if (['admin', 'college'].includes(user.role)) {
      return allowedScholarships.map(scholarship => scholarship.id)
    }
    
    return []
  }, [user, allowedScholarships])

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

  // Get allowed scholarships directly (new method)
  const getAllowedScholarships = useCallback((): AllowedScholarship[] => {
    return allowedScholarships
  }, [allowedScholarships])

  useEffect(() => {
    fetchPermissions()
  }, [fetchPermissions])

  return {
    permissions,
    allowedScholarships,
    isLoading,
    error,
    hasPermission,
    getAllowedScholarshipIds,
    getAllowedScholarships,
    filterScholarshipsByPermission,
    refetch: fetchPermissions
  }
} 
