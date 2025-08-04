/**
 * Type definitions for quota management system
 */

// Enum for quota management modes
export enum QuotaManagementMode {
  NONE = 'none',
  SIMPLE = 'simple',
  COLLEGE_BASED = 'college_based',
  MATRIX_BASED = 'matrix_based'
}

// Individual quota cell data
export interface QuotaCell {
  total_quota: number
  used: number
  available: number
  applications: number
}

// Summary statistics for quotas
export interface QuotaSummary {
  total_quota: number
  total_used: number
  total_available: number
}

// Matrix quota data structure for PhD scholarships
export interface MatrixQuotaData {
  academic_year: string
  period_type: 'academic_year' | 'semester'
  phd_quotas: {
    [subType: string]: {
      [college: string]: QuotaCell
    }
  }
  grand_total: QuotaSummary
}

// Quota overview for a scholarship type
export interface ScholarshipQuotaOverview {
  code: string
  name: string
  name_en: string
  category: string
  has_quota_limit: boolean
  has_college_quota: boolean
  quota_management_mode: string
  application_period: 'semester' | 'academic_year'
  description: string
  sub_types: SubTypeQuota[]
}

// Sub-type quota information
export interface SubTypeQuota {
  main_type: string
  sub_type: string
  scholarship_name: string
  allocated_quota: number
  used_quota: number
  remaining_quota: number
  applications_count: number
  application_period: string
  current_period: string
}

// Update quota request
export interface UpdateMatrixQuotaRequest {
  sub_type: string
  college: string
  new_quota: number
  academic_year?: number
}

// Update quota response
export interface UpdateQuotaResponse {
  sub_type: string
  college: string
  old_quota: number
  new_quota: number
  sub_type_total: number
  grand_total: number
  updated_by: string
  config_id: number
}

// College configuration
export interface CollegeConfig {
  code: string
  name: string
  name_en: string
}

// Sub-type configuration
export interface SubTypeConfig {
  code: string
  name: string
  parent_type: string
}

// Available period (semester or academic year)
export type AvailablePeriod = string // e.g., "114-1" or "114"

// Quota edit event
export interface QuotaEditEvent {
  subType: string
  college: string
  oldValue: number
  newValue: number
  timestamp: Date
}

// Quota usage statistics
export interface QuotaUsageStats {
  totalAllocated: number
  totalUsed: number
  totalAvailable: number
  usagePercentage: number
  warningLevel: 'normal' | 'warning' | 'critical' | 'exceeded'
}

// Matrix table cell props
export interface MatrixCellProps {
  subType: string
  college: string
  data: QuotaCell
  onEdit: (subType: string, college: string, newValue: number) => Promise<void>
  isEditing: boolean
  isLoading: boolean
}

// College and sub-type mappings have been moved to @/lib/college-mappings
// Use getCollegeName() and getSubTypeName() functions instead of hardcoded mappings

// Helper function to calculate warning level
export function getWarningLevel(usagePercentage: number): QuotaUsageStats['warningLevel'] {
  if (usagePercentage >= 100) return 'exceeded'
  if (usagePercentage >= 90) return 'critical'
  if (usagePercentage >= 70) return 'warning'
  return 'normal'
}

// Helper function to get warning color
export function getWarningColor(level: QuotaUsageStats['warningLevel']): string {
  switch (level) {
    case 'exceeded': return 'text-red-600 bg-red-50'
    case 'critical': return 'text-orange-600 bg-orange-50'
    case 'warning': return 'text-yellow-600 bg-yellow-50'
    case 'normal': return 'text-green-600 bg-green-50'
    default: return ''
  }
}