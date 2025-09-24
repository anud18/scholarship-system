/**
 * Matrix quota table component for PhD scholarships
 */

import { useState, useCallback, useEffect } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'
import { Edit2, Check, X, Loader2, AlertCircle } from 'lucide-react'
import { useToast } from '@/components/ui/use-toast'
import {
  MatrixQuotaData,
  QuotaCell,
  getWarningLevel,
  getWarningColor,
} from '@/types/quota'
import { getCollegeName, getCollegeCodes, getSubTypeName, getSubTypeCodes } from '@/lib/college-mappings'
import { quotaApi } from '@/services/api/quotaApi'

interface MatrixQuotaTableProps {
  data: MatrixQuotaData | null
  loading?: boolean
  onDataUpdate?: (data: MatrixQuotaData) => void
  readOnly?: boolean
  currentPeriod?: string
}

interface EditingCell {
  subType: string
  college: string
  value: string
}

export function MatrixQuotaTable({
  data,
  loading = false,
  onDataUpdate,
  readOnly = false,
  currentPeriod,
}: MatrixQuotaTableProps) {
  const { toast } = useToast()
  const [editingCell, setEditingCell] = useState<EditingCell | null>(null)
  const [savingCell, setSavingCell] = useState<string | null>(null)
  const [localData, setLocalData] = useState<MatrixQuotaData | null>(data)

  useEffect(() => {
    setLocalData(data)
  }, [data])

  // Get colleges and sub-types from the actual data, fallback to static lists if no data
  const colleges = localData && Object.keys(localData.phd_quotas).length > 0 
    ? Array.from(new Set(Object.values(localData.phd_quotas).flatMap(subtypeData => Object.keys(subtypeData)))).sort()
    : getCollegeCodes()
  const subTypes = localData ? Object.keys(localData.phd_quotas) : getSubTypeCodes()

  const handleEditStart = (subType: string, college: string, currentValue: number) => {
    if (readOnly) return
    setEditingCell({
      subType,
      college,
      value: currentValue.toString(),
    })
  }

  const handleEditCancel = () => {
    setEditingCell(null)
  }

  const handleEditSave = async () => {
    if (!editingCell || !localData) return

    const newValue = parseInt(editingCell.value)
    if (isNaN(newValue) || newValue < 0) {
      toast({
        title: '錯誤',
        description: '請輸入有效的非負整數',
        variant: 'destructive',
      })
      return
    }

    const cellKey = `${editingCell.subType}-${editingCell.college}`
    setSavingCell(cellKey)

    try {
      // Extract academic year from current period
      const academicYear = currentPeriod ? parseInt(currentPeriod.split('-')[0]) : undefined
      
      const response = await quotaApi.updateMatrixQuota({
        sub_type: editingCell.subType,
        college: editingCell.college,
        new_quota: newValue,
        academic_year: academicYear,
      })

      if (response.success && response.data) {
        // Update local data with deep copy to ensure reactivity
        const updatedData = JSON.parse(JSON.stringify(localData)) as MatrixQuotaData
        updatedData.phd_quotas[editingCell.subType][editingCell.college].total_quota = newValue
        updatedData.phd_quotas[editingCell.subType][editingCell.college].available = 
          newValue - updatedData.phd_quotas[editingCell.subType][editingCell.college].used
        
        // Recalculate all totals comprehensively
        let grandTotal = 0
        let grandUsed = 0
        let grandAvailable = 0
        let grandApplications = 0
        
        Object.values(updatedData.phd_quotas).forEach((colleges) => {
          Object.values(colleges as Record<string, QuotaCell>).forEach((cell) => {
            grandTotal += cell.total_quota
            grandUsed += cell.used
            grandAvailable += cell.available
            grandApplications += cell.applications
          })
        })
        
        updatedData.grand_total = {
          total_quota: grandTotal,
          total_used: grandUsed,
          total_available: grandAvailable,
        }

        // Force state update and callback
        setLocalData(updatedData)
        
        // Use timeout to ensure state has updated before calling parent callback
        setTimeout(() => {
          onDataUpdate?.(updatedData)
        }, 0)

        toast({
          title: '更新成功',
          description: `${getSubTypeName(editingCell.subType)} - ${getCollegeName(editingCell.college)}: ${response.data.old_quota} → ${response.data.new_quota}`,
        })
      } else {
        throw new Error(response.message || '更新失敗')
      }
    } catch (error) {
      toast({
        title: '更新失敗',
        description: error instanceof Error ? error.message : '發生未知錯誤',
        variant: 'destructive',
      })
    } finally {
      setSavingCell(null)
      setEditingCell(null)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      handleEditSave()
    } else if (e.key === 'Escape') {
      handleEditCancel()
    }
  }

  const getCellColor = (cell: QuotaCell) => {
    if (cell.total_quota === 0) return ''
    const percentage = (cell.used / cell.total_quota) * 100
    const level = getWarningLevel(percentage)
    return getWarningColor(level)
  }

  const calculateSubTypeTotal = useCallback((subType: string): QuotaCell => {
    if (!localData) return { total_quota: 0, used: 0, available: 0, applications: 0 }
    
    const result = { total_quota: 0, used: 0, available: 0, applications: 0 }
    Object.values(localData.phd_quotas[subType] || {}).forEach(cell => {
      result.total_quota += cell.total_quota
      result.used += cell.used
      result.available += cell.available
      result.applications += cell.applications
    })
    return result
  }, [localData])

  const calculateCollegeTotal = useCallback((college: string): QuotaCell => {
    if (!localData) return { total_quota: 0, used: 0, available: 0, applications: 0 }
    
    const result = { total_quota: 0, used: 0, available: 0, applications: 0 }
    subTypes.forEach(subType => {
      const cell = localData.phd_quotas[subType]?.[college]
      if (cell) {
        result.total_quota += cell.total_quota
        result.used += cell.used
        result.available += cell.available
        result.applications += cell.applications
      }
    })
    return result
  }, [localData, subTypes])

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
      </div>
    )
  }

  if (!localData) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-gray-500">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p>無配額資料</p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border bg-white shadow-sm overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-32 sticky left-0 bg-white z-10">子類型</TableHead>
            {colleges.map(college => (
              <TableHead key={college} className="text-center min-w-[100px]">
                <div className="flex flex-col">
                  <span className="font-medium">{getCollegeName(college)}</span>
                  <span className="text-xs text-gray-500">({college})</span>
                </div>
              </TableHead>
            ))}
            <TableHead className="text-center font-bold bg-gray-50">總計</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {subTypes.map(subType => {
            const subTypeTotal = calculateSubTypeTotal(subType)
            return (
              <TableRow key={subType}>
                <TableCell className="font-medium sticky left-0 bg-white z-10">
                  <div className="flex flex-col">
                    <span>{getSubTypeName(subType)}</span>
                    <span className="text-xs text-gray-500">({subType})</span>
                  </div>
                </TableCell>
                {colleges.map(college => {
                  const cell = localData.phd_quotas[subType]?.[college] || {
                    total_quota: 0,
                    used: 0,
                    available: 0,
                    applications: 0,
                  }
                  const cellKey = `${subType}-${college}`
                  const isEditing = editingCell?.subType === subType && editingCell?.college === college
                  const isSaving = savingCell === cellKey

                  return (
                    <TableCell key={college} className={cn('text-center p-1', getCellColor(cell))}>
                      {isEditing ? (
                        <div className="flex items-center gap-1 justify-center">
                          <Input
                            type="number"
                            min="0"
                            value={editingCell.value}
                            onChange={(e) =>
                              setEditingCell({ ...editingCell, value: e.target.value })
                            }
                            onKeyDown={handleKeyDown}
                            className="w-20 h-8 text-center"
                            autoFocus
                            disabled={isSaving}
                          />
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={handleEditSave}
                            disabled={isSaving}
                          >
                            {isSaving ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <Check className="h-4 w-4 text-green-600" />
                            )}
                          </Button>
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8"
                            onClick={handleEditCancel}
                            disabled={isSaving}
                          >
                            <X className="h-4 w-4 text-red-600" />
                          </Button>
                        </div>
                      ) : (
                        <div
                          className={cn(
                            'group relative cursor-pointer hover:bg-gray-100 rounded p-2',
                            readOnly && 'cursor-default'
                          )}
                          onClick={() => handleEditStart(subType, college, cell.total_quota)}
                        >
                          <div className="flex flex-col items-center">
                            <div className="flex items-center gap-1">
                              <span className="font-semibold">{cell.total_quota}</span>
                              {!readOnly && (
                                <Edit2 className="h-3 w-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                              )}
                            </div>
                            <div className="text-xs text-gray-500">
                              {cell.used}/{cell.available}
                            </div>
                            {cell.applications > 0 && (
                              <Badge variant="secondary" className="text-xs mt-1">
                                {cell.applications} 申請
                              </Badge>
                            )}
                          </div>
                        </div>
                      )}
                    </TableCell>
                  )
                })}
                <TableCell className="text-center font-bold bg-gray-50">
                  <div className="flex flex-col items-center">
                    <span>{subTypeTotal.total_quota}</span>
                    <span className="text-xs text-gray-500">
                      {subTypeTotal.used}/{subTypeTotal.available}
                    </span>
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
          
          {/* College totals row */}
          <TableRow className="bg-gray-50 font-bold">
            <TableCell className="sticky left-0 bg-gray-50 z-10">學院總計</TableCell>
            {colleges.map(college => {
              const total = calculateCollegeTotal(college)
              return (
                <TableCell key={college} className="text-center">
                  <div className="flex flex-col items-center">
                    <span>{total.total_quota}</span>
                    <span className="text-xs">
                      {total.used}/{total.available}
                    </span>
                  </div>
                </TableCell>
              )
            })}
            <TableCell className="text-center bg-gray-100">
              <div className="flex flex-col items-center">
                <span className="text-lg">{localData.grand_total.total_quota}</span>
                <span className="text-xs">
                  {localData.grand_total.total_used}/{localData.grand_total.total_available}
                </span>
              </div>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>
  )
}
