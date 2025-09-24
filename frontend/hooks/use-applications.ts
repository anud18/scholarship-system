import { useState, useEffect, useCallback } from 'react'
import { apiClient, Application, ApplicationCreate } from '@/lib/api'
import { useAuth } from './use-auth'

export function useApplications() {
  const { isAuthenticated } = useAuth()
  const [applications, setApplications] = useState<Application[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchApplications = useCallback(async (status?: string) => {
    if (!isAuthenticated) {
      console.log('User not authenticated, skipping application fetch')
      return
    }

    try {
      setIsLoading(true)
      setError(null)
      
      const response = await apiClient.applications.getMyApplications(status)
      
      if (Array.isArray(response)) {
        setApplications(response)
      } else if (response.success && response.data) {
        setApplications(response.data)
      } else {
        throw new Error(response.message || 'Failed to fetch applications')
      }
    } catch (err) {
      console.error('Error fetching applications:', err)
      setError(err instanceof Error ? err.message : 'Failed to fetch applications')
    } finally {
      setIsLoading(false)
    }
  }, [isAuthenticated])

  const createApplication = useCallback(async (applicationData: ApplicationCreate, isDraft: boolean = false) => {
    try {
      setError(null)
      
      const response = await apiClient.applications.createApplication(applicationData, isDraft)
      
      if (response.success && response.data) {
        setApplications(prev => [response.data!, ...prev])
        return response.data
      } else {
        throw new Error(response.message || 'Failed to create application')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create application')
      throw err
    }
  }, [])

  const submitApplication = useCallback(async (applicationId: number) => {
    try {
      setError(null)
      
      const response = await apiClient.applications.submitApplication(applicationId)
      
      if (response.success && response.data) {
        setApplications(prev => 
          prev.map(app => app.id === applicationId ? response.data! : app)
        )
        return response.data
      } else {
        throw new Error(response.message || 'Failed to submit application')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to submit application')
      throw err
    }
  }, [])

  const withdrawApplication = useCallback(async (applicationId: number) => {
    try {
      setError(null)
      
      const response = await apiClient.applications.withdrawApplication(applicationId)
      
      if (response.success && response.data) {
        setApplications(prev => 
          prev.map(app => app.id === applicationId ? response.data! : app)
        )
        return response.data
      } else {
        throw new Error(response.message || 'Failed to withdraw application')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to withdraw application')
      throw err
    }
  }, [])

  const updateApplication = useCallback(async (
    applicationId: number, 
    applicationData: Partial<ApplicationCreate>
  ) => {
    try {
      setError(null)
      
      const response = await apiClient.applications.updateApplication(applicationId, applicationData)
      
      if (response.success && response.data) {
        setApplications(prev => 
          prev.map(app => app.id === applicationId ? response.data! : app)
        )
        return response.data
      } else {
        throw new Error(response.message || 'Failed to update application')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update application')
      throw err
    }
  }, [])

  const uploadDocument = useCallback(async (applicationId: number, file: File, fileType: string = 'other') => {
    try {
      setError(null)
      
      const response = await apiClient.applications.uploadDocument(applicationId, file, fileType)
      
      if (response.success) {
        // Refresh applications to get updated document info
        await fetchApplications()
        return response.data
      } else {
        throw new Error(response.message || 'Failed to upload document')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload document')
      throw err
    }
  }, [fetchApplications])

  // Fetch applications on mount - only if authenticated and has token
  useEffect(() => {
    if (isAuthenticated && apiClient.hasToken?.()) {
      fetchApplications()
    }
  }, [fetchApplications, isAuthenticated])

  const saveApplicationDraft = useCallback(async (applicationData: ApplicationCreate) => {
    try {
      setError(null)
      
      const response = await apiClient.applications.saveApplicationDraft(applicationData)
      
      if (response.success && response.data) {
        setApplications(prev => [response.data!, ...prev])
        return response.data
      } else {
        throw new Error(response.message || 'Failed to save draft')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save draft')
      throw err
    }
  }, [])

  const deleteApplication = useCallback(async (applicationId: number) => {
    try {
      setError(null)
      
      const response = await apiClient.applications.deleteApplication(applicationId)
      
      if (response.success) {
        setApplications(prev => prev.filter(app => app.id !== applicationId))
        return response.data
      } else {
        throw new Error(response.message || 'Failed to delete application')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete application')
      throw err
    }
  }, [])

  return {
    applications,
    isLoading,
    error,
    fetchApplications,
    createApplication,
    saveApplicationDraft,
    submitApplication,
    withdrawApplication,
    updateApplication,
    uploadDocument,
    deleteApplication,
  }
} 